import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type ClipboardEvent,
  type DragEvent,
} from "react";
import {
  MAX_REFERENCE_IMAGES,
  MAX_REFERENCE_IMAGE_BYTES,
  type VisionAttachment,
  visionAttachmentLimitError,
} from "./visionImageTypes";
import "./visionImageInput.css";

const SUPPORTED_MEDIA_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

type Props = {
  scopeId: string;
  images: VisionAttachment[];
  onChange: (images: VisionAttachment[]) => void;
  disabled?: boolean;
};

function formatBytes(value: number): string {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function inferredMediaType(file: File): VisionAttachment["media_type"] | null {
  if (SUPPORTED_MEDIA_TYPES.has(file.type)) return file.type as VisionAttachment["media_type"];
  const extension = file.name.toLowerCase().split(".").at(-1);
  if (extension === "png") return "image/png";
  if (extension === "jpg" || extension === "jpeg") return "image/jpeg";
  if (extension === "webp") return "image/webp";
  return null;
}

function readDataUrl(file: File, mediaType: VisionAttachment["media_type"]): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result !== "string") {
        reject(new Error("图片读取结果无效"));
        return;
      }
      const comma = reader.result.indexOf(",");
      if (comma < 0) {
        reject(new Error("图片编码结果无效"));
        return;
      }
      resolve(`data:${mediaType};base64,${reader.result.slice(comma + 1)}`);
    };
    reader.onerror = () => reject(reader.error ?? new Error("图片读取失败"));
    reader.readAsDataURL(file);
  });
}

export function VisionImageInput({ scopeId, images, onChange, disabled = false }: Props) {
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [processing, setProcessing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const imagesRef = useRef(images);
  const scopeRef = useRef(scopeId);
  const scopeGeneration = useRef(0);
  const uploadQueue = useRef<Promise<void>>(Promise.resolve());

  if (scopeRef.current !== scopeId) {
    scopeRef.current = scopeId;
    scopeGeneration.current += 1;
    imagesRef.current = images;
  }

  useEffect(() => {
    imagesRef.current = images;
  }, [images]);

  const commit = (next: VisionAttachment[]) => {
    const limitError = visionAttachmentLimitError(next);
    if (limitError) throw new Error(limitError);
    imagesRef.current = next;
    onChange(next);
  };

  const addFiles = (files: File[]) => {
    if (!files.length || disabled) return;
    const queuedScopeGeneration = scopeGeneration.current;
    uploadQueue.current = uploadQueue.current
      .catch(() => undefined)
      .then(async () => {
        setProcessing(true);
        setError("");
        const decoded: VisionAttachment[] = [];
        for (const file of files) {
          const mediaType = inferredMediaType(file);
          if (!mediaType) throw new Error(`${file.name} 不是支持的 PNG、JPEG 或 WebP 图片。`);
          if (file.size <= 0) throw new Error(`${file.name} 是空文件。`);
          if (file.size > MAX_REFERENCE_IMAGE_BYTES) {
            throw new Error(`${file.name} 超过单张 ${formatBytes(MAX_REFERENCE_IMAGE_BYTES)} 的限制。`);
          }
          decoded.push({
            id: crypto.randomUUID(),
            name: file.name.slice(0, 200),
            media_type: mediaType,
            data_url: await readDataUrl(file, mediaType),
            detail: "high",
            size_bytes: file.size,
          });
        }

        // Re-read the authoritative attachment list after every asynchronous file read.
        // This final validation prevents two rapid uploads from both passing against an old snapshot.
        if (queuedScopeGeneration !== scopeGeneration.current) return;
        commit([...imagesRef.current, ...decoded]);
      })
      .catch((nextError) => {
        setError(nextError instanceof Error ? nextError.message : String(nextError));
      })
      .finally(() => setProcessing(false));
  };

  const onInput = (event: ChangeEvent<HTMLInputElement>) => {
    addFiles(Array.from(event.target.files ?? []));
    event.target.value = "";
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    addFiles(Array.from(event.dataTransfer.files));
  };

  const onPaste = (event: ClipboardEvent<HTMLDivElement>) => {
    const files = Array.from(event.clipboardData.files);
    if (!files.length) return;
    event.preventDefault();
    addFiles(files);
  };

  const removeImage = (id: string) => {
    const next = imagesRef.current.filter((image) => image.id !== id);
    imagesRef.current = next;
    onChange(next);
  };

  const clearImages = () => {
    imagesRef.current = [];
    onChange([]);
    setError("");
  };

  return (
    <section className="vision-image-input" aria-label="视觉参考图片">
      <input
        ref={inputRef}
        data-testid="agent-reference-image-input"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        multiple
        hidden
        disabled={disabled || processing}
        onChange={onInput}
      />
      <div
        className={`vision-image-dropzone${dragging ? " dragging" : ""}`}
        tabIndex={0}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
        }}
        onDrop={onDrop}
        onPaste={onPaste}
      >
        <div>
          <strong>参考图片</strong>
          <span>与自然语言一起发送给支持识图的模型</span>
        </div>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={disabled || processing || images.length >= MAX_REFERENCE_IMAGES}
        >
          {processing ? "读取中…" : "上传图片"}
        </button>
        <small>可选择、拖入或粘贴 PNG/JPEG/WebP；最多 {MAX_REFERENCE_IMAGES} 张，单张 8 MB。</small>
      </div>
      {images.length ? <div className="vision-image-list" data-testid="agent-reference-image-list">
        {images.map((image) => <article key={image.id}>
          <img src={image.data_url} alt={image.name} />
          <div><strong title={image.name}>{image.name}</strong><span>{formatBytes(image.size_bytes)}</span></div>
          <button
            type="button"
            aria-label={`移除参考图 ${image.name}`}
            disabled={disabled || processing}
            onClick={() => removeImage(image.id)}
          >移除</button>
        </article>)}
        <div className="vision-image-summary">
          已附加 {images.length} 张 · {formatBytes(images.reduce((sum, image) => sum + image.size_bytes, 0))}
          <button type="button" disabled={disabled || processing} onClick={clearImages}>全部清除</button>
        </div>
      </div> : null}
      {error ? <div className="vision-image-error" role="alert">{error}</div> : null}
      <p>图片只保存在当前页面内存并通过正式 Agent API 随规划/重规划请求发送，不写入项目数据库。所选模型必须支持视觉输入。</p>
    </section>
  );
}
