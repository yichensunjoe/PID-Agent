import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type ClipboardEvent,
  type DragEvent,
} from "react";
import { createPortal } from "react-dom";
import { useWorkspace } from "../store";
import "./visionImageInput.css";

const MAX_IMAGES = 4;
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const MAX_TOTAL_BYTES = 16 * 1024 * 1024;
const SUPPORTED_MEDIA_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const APPLY_EVENT = "pid-agent:vision-images-applied";

type VisionAttachment = {
  id: string;
  name: string;
  mediaType: "image/png" | "image/jpeg" | "image/webp";
  dataUrl: string;
  sizeBytes: number;
};

type RequestImage = {
  name: string;
  media_type: VisionAttachment["mediaType"];
  data_url: string;
  detail: "high";
};

function formatBytes(value: number): string {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function inferredMediaType(file: File): VisionAttachment["mediaType"] | null {
  if (SUPPORTED_MEDIA_TYPES.has(file.type)) return file.type as VisionAttachment["mediaType"];
  const extension = file.name.toLowerCase().split(".").at(-1);
  if (extension === "png") return "image/png";
  if (extension === "jpg" || extension === "jpeg") return "image/jpeg";
  if (extension === "webp") return "image/webp";
  return null;
}

function readDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => typeof reader.result === "string"
      ? resolve(reader.result)
      : reject(new Error("图片读取结果无效"));
    reader.onerror = () => reject(reader.error ?? new Error("图片读取失败"));
    reader.readAsDataURL(file);
  });
}

function requestPath(input: RequestInfo | URL): string {
  const value = input instanceof Request ? input.url : input instanceof URL ? input.href : input;
  return new URL(value, window.location.href).pathname;
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) return init.method.toUpperCase();
  return input instanceof Request ? input.method.toUpperCase() : "GET";
}

function toRequestImages(images: VisionAttachment[]): RequestImage[] {
  return images.map((image) => ({
    name: image.name,
    media_type: image.mediaType,
    data_url: image.dataUrl,
    detail: "high",
  }));
}

function createPortalHost(): HTMLDivElement | null {
  const label = document.querySelector<HTMLElement>(".agent-panel > label:first-of-type");
  if (!label?.parentElement) return null;
  const existing = label.parentElement.querySelector<HTMLDivElement>(".vision-image-portal-host");
  if (existing) return existing;
  const host = document.createElement("div");
  host.className = "vision-image-portal-host";
  label.insertAdjacentElement("afterend", host);
  return host;
}

export function VisionImageInputEnhancements() {
  const documentId = useWorkspace((state) => state.document?.id ?? "");
  const [host, setHost] = useState<HTMLDivElement | null>(() => createPortalHost());
  const [images, setImages] = useState<VisionAttachment[]>([]);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const imagesRef = useRef<VisionAttachment[]>([]);
  const previousDocumentId = useRef(documentId);

  useEffect(() => {
    imagesRef.current = images;
  }, [images]);

  useEffect(() => {
    const update = () => setHost(createPortalHost());
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (previousDocumentId.current && previousDocumentId.current !== documentId) {
      setImages([]);
      setError("");
    }
    previousDocumentId.current = documentId;
  }, [documentId]);

  useEffect(() => {
    const clear = () => {
      setImages([]);
      setError("");
    };
    window.addEventListener(APPLY_EVENT, clear);
    return () => window.removeEventListener(APPLY_EVENT, clear);
  }, []);

  useEffect(() => {
    const originalFetch = window.fetch.bind(window);
    const enhancedFetch: typeof window.fetch = async (input, init) => {
      const path = requestPath(input);
      const method = requestMethod(input, init);
      const isPlanningRequest = method === "POST" && (
        path.endsWith("/agent/plan-v2") || path.endsWith("/agent/replan")
      );
      let nextInit = init;
      if (isPlanningRequest && imagesRef.current.length && typeof init?.body === "string") {
        try {
          const payload = JSON.parse(init.body) as Record<string, unknown>;
          payload.images = toRequestImages(imagesRef.current);
          nextInit = { ...init, body: JSON.stringify(payload) };
        } catch {
          // Preserve the original request. The normal API error path remains authoritative.
        }
      }
      const response = await originalFetch(input, nextInit);
      if (method === "POST" && path.endsWith("/agent/apply-v2") && response.ok) {
        window.dispatchEvent(new Event(APPLY_EVENT));
      }
      return response;
    };
    window.fetch = enhancedFetch;
    return () => {
      if (window.fetch === enhancedFetch) window.fetch = originalFetch;
    };
  }, []);

  const addFiles = async (files: File[]) => {
    if (!files.length) return;
    setError("");
    const current = imagesRef.current;
    if (current.length + files.length > MAX_IMAGES) {
      setError(`最多上传 ${MAX_IMAGES} 张参考图。`);
      return;
    }
    const accepted: VisionAttachment[] = [];
    let totalBytes = current.reduce((sum, image) => sum + image.sizeBytes, 0);
    try {
      for (const file of files) {
        const mediaType = inferredMediaType(file);
        if (!mediaType) throw new Error(`${file.name} 不是支持的 PNG、JPEG 或 WebP 图片。`);
        if (file.size <= 0) throw new Error(`${file.name} 是空文件。`);
        if (file.size > MAX_IMAGE_BYTES) {
          throw new Error(`${file.name} 超过单张 ${formatBytes(MAX_IMAGE_BYTES)} 的限制。`);
        }
        totalBytes += file.size;
        if (totalBytes > MAX_TOTAL_BYTES) {
          throw new Error(`参考图总大小不能超过 ${formatBytes(MAX_TOTAL_BYTES)}。`);
        }
        const dataUrl = await readDataUrl(file);
        accepted.push({
          id: crypto.randomUUID(),
          name: file.name.slice(0, 200),
          mediaType,
          dataUrl,
          sizeBytes: file.size,
        });
      }
      setImages((value) => [...value, ...accepted]);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    }
  };

  const onInput = (event: ChangeEvent<HTMLInputElement>) => {
    void addFiles(Array.from(event.target.files ?? []));
    event.target.value = "";
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    void addFiles(Array.from(event.dataTransfer.files));
  };

  const onPaste = (event: ClipboardEvent<HTMLDivElement>) => {
    const files = Array.from(event.clipboardData.files);
    if (!files.length) return;
    event.preventDefault();
    void addFiles(files);
  };

  if (!host) return null;

  return createPortal(
    <section className="vision-image-input" aria-label="视觉参考图片">
      <input
        ref={inputRef}
        data-testid="agent-reference-image-input"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        multiple
        hidden
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
          disabled={images.length >= MAX_IMAGES}
        >
          上传图片
        </button>
        <small>可选择、拖入或粘贴 PNG/JPEG/WebP；最多 {MAX_IMAGES} 张，单张 8 MB。</small>
      </div>
      {images.length ? <div className="vision-image-list" data-testid="agent-reference-image-list">
        {images.map((image) => <article key={image.id}>
          <img src={image.dataUrl} alt={image.name} />
          <div><strong title={image.name}>{image.name}</strong><span>{formatBytes(image.sizeBytes)}</span></div>
          <button
            type="button"
            aria-label={`移除参考图 ${image.name}`}
            onClick={() => setImages((value) => value.filter((item) => item.id !== image.id))}
          >移除</button>
        </article>)}
        <div className="vision-image-summary">
          已附加 {images.length} 张 · {formatBytes(images.reduce((sum, image) => sum + image.sizeBytes, 0))}
          <button type="button" onClick={() => setImages([])}>全部清除</button>
        </div>
      </div> : null}
      {error ? <div className="vision-image-error" role="alert">{error}</div> : null}
      <p>图片仅保存在当前页面内存并随规划/重规划请求发送，不写入项目数据库。所选模型必须支持视觉输入。</p>
    </section>,
    host,
  );
}
