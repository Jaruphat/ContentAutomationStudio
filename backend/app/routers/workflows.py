"""
Workflows router - Import, validate, and manage ComfyUI workflow registrations.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Workflow
from app.schemas import (
    DependencyReportOut,
    MappingCandidateOut,
    SubgraphInfoOut,
    WorkflowAnalysisResult,
    WorkflowMappingUpdate,
    WorkflowResponse,
    WorkflowValidationResult,
)
from app.services import (
    workflow_analysis,
    workflow_dependencies,
    workflow_registry,
)
from app.services.queue_manager import queue_manager
from app.services.workflow_format import WorkflowFormat

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.post("/import", response_model=WorkflowResponse, status_code=201)
def import_workflow(
    file: UploadFile = File(...),
    name: str = Form(...),
    purpose: str = Form("image"),
    version: str = Form("1.0"),
    tested_comfyui_version: str = Form(""),
    db: Session = Depends(get_db),
):
    """
    Import a ComfyUI API-format workflow JSON file.

    Parses the file, computes SHA-256, stores the source JSON, and creates
    a Workflow record. The parameter_mapping and output_mapping start empty
    and must be configured separately.
    """
    raw_bytes = file.file.read()

    try:
        record_data = workflow_registry.import_workflow(
            raw_bytes=raw_bytes,
            name=name,
            purpose=purpose,
            version=version,
            tested_comfyui_version=tested_comfyui_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    workflow = Workflow(**record_data)
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


@router.get("", response_model=list[WorkflowResponse])
def list_workflows(db: Session = Depends(get_db)):
    return db.query(Workflow).order_by(Workflow.created_at.desc()).all()


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.put("/{workflow_id}/mapping", response_model=WorkflowResponse)
def update_mapping(
    workflow_id: str,
    payload: WorkflowMappingUpdate,
    db: Session = Depends(get_db),
):
    """Update the parameter_mapping and output_mapping for a workflow."""
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow.parameter_mapping = payload.parameter_mapping
    if payload.output_mapping:
        workflow.output_mapping = payload.output_mapping
    workflow.validation_status = "pending"
    workflow.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(workflow)
    return workflow


@router.post("/{workflow_id}/validate", response_model=WorkflowValidationResult)
def validate_workflow(workflow_id: str, db: Session = Depends(get_db)):
    """
    Validate the current parameter/output mapping against the stored
    workflow JSON source.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if not workflow.source_json_path:
        raise HTTPException(
            status_code=400,
            detail="No source JSON path recorded for this workflow",
        )

    try:
        workflow_data = workflow_registry.load_workflow_source(workflow.source_json_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"Source JSON file not found: {workflow.source_json_path}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    is_valid, errors, warnings = workflow_registry.validate_mapping(
        workflow_data=workflow_data,
        parameter_mapping=workflow.parameter_mapping or {},
        output_mapping=workflow.output_mapping or [],
    )

    # Update validation status in DB
    workflow.validation_status = "valid" if is_valid else "invalid"
    workflow.updated_at = datetime.now(timezone.utc)
    db.commit()

    return WorkflowValidationResult(
        valid=is_valid,
        errors=errors,
        warnings=warnings,
    )


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(workflow_id: str, db: Session = Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.delete(workflow)
    db.commit()
    return None


@router.get("/{workflow_id}/analysis", response_model=WorkflowAnalysisResult)
async def analyse_workflow(workflow_id: str, db: Session = Depends(get_db)):
    """
    Diagnose a registered workflow.

    Reports which ComfyUI JSON shape it is and why, inventories the node
    classes and model files it needs (looking inside subgraphs), proposes
    candidate logical-field mappings, and checks those requirements against the
    live instance's /object_info catalogue when one is reachable.

    Works for both formats. A UI-format workflow is analysed but reported as
    not submittable, with the export step spelled out.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    try:
        data = workflow_registry.load_workflow_source(workflow.source_json_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=400,
            detail=f"Source JSON file not found: {workflow.source_json_path}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    analysis = workflow_analysis.analyze_workflow(data)

    # Check requirements against the live catalogue when the provider has one.
    object_info = await queue_manager.provider.get_object_info()
    report = workflow_dependencies.check_dependencies(analysis, object_info)

    blocking_reason = ""
    if analysis.format is not WorkflowFormat.API:
        blocking_reason = (
            f"This workflow is {analysis.format.value}-format JSON. ComfyUI's "
            f"/prompt endpoint only accepts API-format. In ComfyUI open the "
            f"workflow and choose Workflow -> Export (API), then import that "
            f"file here and map its nodes."
        )

    return WorkflowAnalysisResult(
        workflow_id=workflow.id,
        name=workflow.name,
        format=analysis.format.value,
        format_confidence=analysis.format_confidence,
        format_reasons=analysis.format_reasons,
        submittable=analysis.submittable,
        blocking_reason=blocking_reason,
        node_count=len(analysis.nodes),
        subgraphs=[
            SubgraphInfoOut(
                subgraph_id=sg.subgraph_id,
                name=sg.name,
                input_bindings=sg.input_bindings,
                inner_node_classes=sg.inner_node_classes,
                unresolved_inputs=sg.unresolved_inputs,
            )
            for sg in analysis.subgraphs
        ],
        required_node_classes=analysis.required_node_classes,
        frontend_only_node_classes=analysis.frontend_only_node_classes,
        required_models=analysis.required_models,
        mapping_candidates=[
            MappingCandidateOut(**vars(c)) for c in analysis.mapping_candidates
        ],
        alternate_candidates=[
            MappingCandidateOut(**vars(c)) for c in analysis.alternate_candidates
        ],
        unmapped_logical_fields=analysis.unmapped_logical_fields,
        suggested_parameter_mapping=workflow_analysis.suggested_parameter_mapping(
            analysis
        ),
        dependencies=DependencyReportOut(
            checked=report.checked,
            reason=report.reason,
            satisfied=report.satisfied,
            summary=report.summary(),
            node_classes_present=report.node_classes_present,
            node_classes_missing=report.node_classes_missing,
            node_classes_frontend_only=report.node_classes_frontend_only,
            models_present=report.models_present,
            models_missing=report.models_missing,
            catalogue_size=report.catalogue_size,
        ),
        warnings=analysis.warnings,
    )
