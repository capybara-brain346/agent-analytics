import { useRef, useState } from "react";
import { Check, CircleAlert, Info, Upload } from "lucide-react";
import { ApiError, apiPost } from "@/lib/api/client";
import type { IngestAccepted } from "@/lib/api/types";
import { parseLogName } from "@/lib/log-name";
import { Select } from "../../shared";
import { sourceName } from "./format";

export type UploadItem = {
  name: string;
  site: string;
  source: string;
  status: "waiting" | "uploading" | "accepted" | "duplicate" | "failed";
  fileId?: string;
  error?: string;
};

export type UploadState = {
  site: string;
  sources: string[];
  source: string;
  setSource: (s: string) => void;
  busy: boolean;
  items: UploadItem[];
  send: (files: File[]) => void;
};

const NO_SITE =
  "No site. Select a site, or name the file <site>__<source>__<start>.log.";

/**
 * POST /api/imports/upload, one request per file, one file at a time.
 * Site and source come from the file name (samples/logs/README.md). A file
 * without that name uses the selected site and source.
 */
export function useUpload(
  scopeSite: string,
  fallbackSite: string | undefined,
  sources: string[],
  done: () => void,
): UploadState {
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [items, setItems] = useState<UploadItem[]>([]);
  const site = scopeSite || fallbackSite || "";
  const chosen = sources.includes(source) ? source : (sources[0] ?? "");

  const send = async (files: File[]) => {
    const named = files
      .map((file) => ({ file, name: parseLogName(file.name) }))
      .sort(
        (a, b) =>
          (a.name?.start ?? "").localeCompare(b.name?.start ?? "") ||
          a.file.name.localeCompare(b.file.name),
      );
    const list: UploadItem[] = named.map(({ file, name }) => ({
      name: file.name,
      site: name?.site ?? site,
      source: name?.source ?? chosen,
      status: "waiting",
    }));
    const update = (i: number, patch: Partial<UploadItem>) => {
      list[i] = { ...list[i], ...patch };
      setItems([...list]);
    };

    setBusy(true);
    setItems([...list]);
    for (const [i, { file }] of named.entries()) {
      if (!list[i].site) {
        update(i, { status: "failed", error: NO_SITE });
        continue;
      }

      update(i, { status: "uploading" });
      try {
        const r = await apiPost<IngestAccepted>(
          "imports/upload",
          { site: list[i].site, source: list[i].source },
          file,
        );
        update(i, {
          status: r.duplicate ? "duplicate" : "accepted",
          fileId: r.file_id,
        });
      } catch (e) {
        update(i, {
          status: "failed",
          error: e instanceof ApiError ? e.message : String(e),
        });
      }
    }
    setBusy(false);
    done();
  };

  return {
    site,
    sources,
    source: chosen,
    setSource,
    busy,
    items,
    send: (files) => void send(files),
  };
}

/** Source select and the one primary button of the screen. */
export function UploadControls({ upload }: { upload: UploadState }) {
  const input = useRef<HTMLInputElement>(null);

  return (
    <div className="upload-group">
      {upload.sources.length > 1 && (
        <Select
          label="Source of a file whose name has no source"
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
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length) upload.send(files);
        }}
      />
      <button
        type="button"
        className="btn-primary"
        disabled={upload.busy}
        title="Upload log files. Or drop them on this tab."
        onClick={() => input.current?.click()}
      >
        <Upload size={14} />
        {upload.busy ? "Uploading…" : "Upload log files"}
      </button>
    </div>
  );
}

/** Drop target for log files. The upload button is the keyboard path. */
export function UploadDropZone({
  upload,
  children,
}: {
  upload: UploadState;
  children: React.ReactNode;
}) {
  const [over, setOver] = useState(false);
  const hasFiles = (e: React.DragEvent) =>
    Array.from(e.dataTransfer.types).includes("Files");

  return (
    <div
      className={over ? "upload-drop is-over" : "upload-drop"}
      onDragOver={(e) => {
        if (!hasFiles(e) || upload.busy) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
        setOver(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null))
          setOver(false);
      }}
      onDrop={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault();
        setOver(false);
        const files = Array.from(e.dataTransfer.files);
        if (files.length && !upload.busy) upload.send(files);
      }}
    >
      {children}
      {over && (
        <div className="upload-drop-overlay" aria-hidden>
          <Upload size={18} />
          Drop log files to upload
        </div>
      )}
    </div>
  );
}

const ITEM_TEXT: Record<UploadItem["status"], string> = {
  waiting: "Waiting",
  uploading: "Uploading…",
  accepted: "Accepted. Queued until the import runs.",
  duplicate: "Already stored. Not added again.",
  failed: "Failed",
};

export function UploadResult({ upload }: { upload: UploadState }) {
  if (!upload.items.length) return null;

  return (
    <div className="notice upload-results" role="status">
      <ul>
        {upload.items.map((item, i) => (
          <li key={`${item.name}-${i}`} data-status={item.status}>
            {item.status === "failed" ? (
              <CircleAlert size={14} />
            ) : item.status === "accepted" || item.status === "duplicate" ? (
              <Check size={14} />
            ) : (
              <Info size={14} />
            )}
            <code>{item.name}</code>
            <span className="faint">
              {item.site || "—"} · {item.source ? sourceName(item.source) : "—"}
            </span>
            <span>
              {item.error ?? ITEM_TEXT[item.status]}
              {item.fileId && (
                <>
                  {" "}
                  File ID <code>{item.fileId}</code>
                </>
              )}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
