export const MAX_REFERENCE_IMAGES = 4;
export const MAX_REFERENCE_IMAGE_BYTES = 8 * 1024 * 1024;
export const MAX_REFERENCE_IMAGE_TOTAL_BYTES = 16 * 1024 * 1024;

export type AgentImagePayload = {
  name: string;
  media_type: "image/png" | "image/jpeg" | "image/webp";
  data_url: string;
  detail: "high";
};

export type VisionAttachment = AgentImagePayload & {
  id: string;
  size_bytes: number;
};

export function visionAttachmentLimitError(images: VisionAttachment[]): string | null {
  if (images.length > MAX_REFERENCE_IMAGES) return `最多上传 ${MAX_REFERENCE_IMAGES} 张参考图。`;
  const oversized = images.find((image) => image.size_bytes > MAX_REFERENCE_IMAGE_BYTES);
  if (oversized) return `${oversized.name} 超过单张 8 MB 的限制。`;
  const total = images.reduce((sum, image) => sum + image.size_bytes, 0);
  if (total > MAX_REFERENCE_IMAGE_TOTAL_BYTES) return "参考图总大小不能超过 16 MB。";
  return null;
}

export function toAgentImagePayload(images: VisionAttachment[]): AgentImagePayload[] {
  return images.map(({ name, media_type, data_url, detail }) => ({
    name,
    media_type,
    data_url,
    detail,
  }));
}
