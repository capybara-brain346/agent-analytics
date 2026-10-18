import { useRef, useState } from "react";
import { Check, Info, Upload } from "lucide-react";
import { ApiError, apiPost } from "@/lib/api/client";
import type { IngestAccepted } from "@/lib/api/types";
import { ErrorState, Select } from "../../shared";
import { sourceName } from "./format";

export type UploadState = {
  site: string;
  sources: string[];
  source: string;
  setSource: (s: string) => void;
  busy: boolean;
  result: IngestAccepted | null;
  error: ApiError | null;
  send: (file: File) => void;
};

/** POST /api/imports/upload */
export function useUpload(
  scopeSite: string,
  fallbackSite: string | undefined,
  sources: string[],
  done: () => void,
): UploadState {
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<IngestAccepted | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const site = scopeSite || fallbackSite || "";
  const chosen = sources.includes(source) ? source : (sources[0] ?? "");

  const send = (file: File) => {
    setBusy(true);
    setResult(null);
    setError(null);
    apiPost<IngestAccepted>(
      "imports/upload",
      { site, source: chosen },
      file,
    ).then(
      (r) => {
        setResult(r);
        setBusy(false);
        done();
      },
      (e: unknown) => {
        setError(
          e instanceof ApiError
            ? e
            : new ApiError(0, "client_error", String(e)),
        );
        setBusy(false);
      },
    );
  };

  return {
    site,
    sources,
    source: chosen,
    setSource,
    busy,
    result,
    error,
    send,
  };
}

/** Source select and the one primary button of the screen. */
export function UploadControls({ upload }: { upload: UploadState }) {
  const input = useRef<HTMLInputElement>(null);
  const disabled = upload.busy || !upload.site || !upload.source;

  return (
    <div className="upload-group">
      {upload.sources.length > 1 && (
        <Select
          label="Source of the file"
          value={upload.source}
          onChange={upload.setSource}
          options={upload.sources.map((s) => ({
            value: s,
            label: sourceName(s),
          }))}
        />
      )}
      <input
        ref={input}
        type="file"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) upload.send(file);
        }}
      />
      <button
        type="button"
        className="btn-primary"
        disabled={disabled}
        title={
          upload.site
            ? `Upload a log file for ${upload.site} (${upload.source})`
            : "Select a site first"
        }
        onClick={() => input.current?.click()}
      >
        <Upload size={14} />
        {upload.busy ? "Uploading…" : "Upload log file"}
      </button>
    </div>
  );
}

export function UploadResult({ upload }: { upload: UploadState }) {
  if (upload.busy)
    return (
      <div className="notice compact-notice" role="status">
        <Info size={14} />
        <span>
          Uploading to {upload.site} ({upload.source})…
        </span>
      </div>
    );

  if (upload.error)
    return <ErrorState error={upload.error} title="Upload failed" />;

  if (upload.result)
    return (
      <div className="notice compact-notice" role="status">
        <Check size={14} />
        <span>
          {upload.result.duplicate
            ? "This file is already stored. It was not added again."
            : "File accepted. It is queued until the import runs."}{" "}
          File ID <code>{upload.result.file_id}</code>
        </span>
      </div>
    );

  return null;
}
