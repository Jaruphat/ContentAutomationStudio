import type {
  GenerationMode,
  MediaProviderCatalogue,
  MediaProviderId,
} from "../types";

interface MediaProviderFieldsProps {
  catalogue: MediaProviderCatalogue | undefined;
  generationMode: GenerationMode;
  providerId: MediaProviderId;
  model: string;
  onProviderChange: (providerId: MediaProviderId, defaultModel: string) => void;
  onModelChange: (model: string) => void;
}

/** Per-shot routing controls. Video remains on the catalogue's video provider. */
export default function MediaProviderFields({
  catalogue,
  generationMode,
  providerId,
  model,
  onProviderChange,
  onModelChange,
}: MediaProviderFieldsProps) {
  if (!catalogue) {
    return <p className="text-xs text-zinc-500">Loading media providers...</p>;
  }

  const videoProvider = catalogue.providers.find(
    (provider) => provider.id === catalogue.video_provider_id,
  );
  if (generationMode !== "image") {
    return (
      <p className="text-xs text-zinc-500">
        Video uses {videoProvider?.label ?? catalogue.video_provider_id}.
      </p>
    );
  }

  const imageProviders = catalogue.providers.filter((provider) =>
    provider.media_types.includes("image"),
  );
  const selected =
    imageProviders.find((provider) => provider.id === providerId) ??
    imageProviders.find(
      (provider) => provider.id === catalogue.default_image_provider_id,
    ) ??
    imageProviders[0];

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <div>
        <label className="text-[10px] uppercase text-zinc-500" htmlFor="shot-image-provider">
          Image provider
        </label>
        <select
          id="shot-image-provider"
          aria-label="Image provider"
          value={selected?.id ?? providerId}
          onChange={(event) => {
            const next = imageProviders.find(
              (provider) => provider.id === event.target.value,
            );
            if (next) onProviderChange(next.id, next.default_model);
          }}
          className="w-full rounded px-2 py-1 text-xs"
        >
          {imageProviders.map((provider) => (
            <option key={provider.id} value={provider.id}>
              {provider.label}
              {!provider.configured ? " (not configured)" : ""}
              {provider.mock ? " (mock)" : ""}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="text-[10px] uppercase text-zinc-500" htmlFor="shot-image-model">
          Image model
        </label>
        <select
          id="shot-image-model"
          aria-label="Image model"
          value={model || selected?.default_model || ""}
          onChange={(event) => onModelChange(event.target.value)}
          className="w-full rounded px-2 py-1 text-xs"
        >
          {(selected?.models ?? []).map((entry) => (
            <option key={entry.id} value={entry.id}>
              {entry.label}
            </option>
          ))}
        </select>
        {selected?.requires_confirmation && (
          <p className="mt-1 text-[10px] text-amber-400">
            Metered provider; cost confirmation is required before generation.
          </p>
        )}
      </div>
    </div>
  );
}
