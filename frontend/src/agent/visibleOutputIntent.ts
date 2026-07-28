const VISIBLE_DRAWING_INTENT = /(?:p\s*&?\s*id|pid|流程图|工艺图|绘制|画出|作图|生成.{0,8}(?:图|流程)|设备|泵|阀|罐|塔|换热器|压缩机|管线|管道|仪表|测点)/i;
const STRUCTURE_ONLY_INTENT = /^(?:请)?\s*(?:只|仅)?\s*(?:新增|添加|创建|建立|重命名|删除|管理|设置|修改)\s*.{0,20}(?:图层|系统)\s*[。.!！]?$/i;

export function shouldRequireVisibleOutput(prompt: string, currentElementCount: number): boolean {
  if (currentElementCount > 0) return false;
  const normalized = prompt.trim();
  if (!normalized || STRUCTURE_ONLY_INTENT.test(normalized)) return false;
  return VISIBLE_DRAWING_INTENT.test(normalized);
}
