import { useMemo, useState } from "react";
import type { DocumentSummary, ProjectFolder } from "../types";
import { useWorkspace } from "../store";

type DocumentTreeProps = {
  documents: DocumentSummary[];
  activeDocumentId?: string;
  folders: ProjectFolder[];
  busy: boolean;
  onOpenDocument: (id: string) => void;
  onDeleteDocument: (document: DocumentSummary) => void;
  onCreateDocumentInFolder: (folderId?: string) => void;
  onCreateFolder: () => void;
  onRenameFolder: (folder: ProjectFolder) => void;
  onDeleteFolder: (folder: ProjectFolder) => void;
  onMoveDocument: (documentId: string, folderId: string) => void;
};

export function DocumentTree({
  documents,
  activeDocumentId,
  folders,
  busy,
  onOpenDocument,
  onDeleteDocument,
  onCreateDocumentInFolder,
  onCreateFolder,
  onRenameFolder,
  onDeleteFolder,
  onMoveDocument,
}: DocumentTreeProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [collapsedFolderIds, setCollapsedFolderIds] = useState<Record<string, boolean>>({});

  const toggleFolderCollapse = (folderId: string) => {
    setCollapsedFolderIds((prev) => ({
      ...prev,
      [folderId]: !prev[folderId],
    }));
  };

  const allFolderKeys = useMemo(() => [...folders.map((f) => f.id), "_uncategorized"], [folders]);
  const areAllCollapsed = useMemo(() => {
    return allFolderKeys.length > 0 && allFolderKeys.every((k) => collapsedFolderIds[k]);
  }, [allFolderKeys, collapsedFolderIds]);

  const toggleAllCollapse = () => {
    if (areAllCollapsed) {
      setCollapsedFolderIds({});
    } else {
      const next: Record<string, boolean> = {};
      for (const k of allFolderKeys) next[k] = true;
      setCollapsedFolderIds(next);
    }
  };

  const normalizedQuery = searchQuery.trim().toLowerCase();

  // Categorize documents
  const { folderMap, uncategorizedDocs } = useMemo(() => {
    const map: Record<string, DocumentSummary[]> = {};
    for (const f of folders) {
      map[f.id] = [];
    }
    const uncategorized: DocumentSummary[] = [];

    for (const doc of documents) {
      const docFolderId = String(doc.metadata?.folder_id ?? "");
      if (docFolderId && map[docFolderId]) {
        map[docFolderId].push(doc);
      } else {
        uncategorized.push(doc);
      }
    }
    return { folderMap: map, uncategorizedDocs: uncategorized };
  }, [documents, folders]);

  // Filter based on search query
  const filteredFolders = useMemo(() => {
    if (!normalizedQuery) return folders;
    return folders.filter((folder) => {
      const folderMatches = folder.name.toLowerCase().includes(normalizedQuery);
      const docs = folderMap[folder.id] ?? [];
      const hasMatchingDoc = docs.some((doc) =>
        doc.name.toLowerCase().includes(normalizedQuery),
      );
      return folderMatches || hasMatchingDoc;
    });
  }, [folders, folderMap, normalizedQuery]);

  const filterDocs = (docs: DocumentSummary[]) => {
    if (!normalizedQuery) return docs;
    return docs.filter((doc) => doc.name.toLowerCase().includes(normalizedQuery));
  };

  return (
    <div className="document-tree-container">
      <div className="document-tree-toolbar">
        <div className="document-search-row">
          <input
            type="text"
            className="document-search-input"
            placeholder="搜索图纸或项目分类…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery ? (
            <button
              type="button"
              className="search-clear-btn"
              onClick={() => setSearchQuery("")}
              title="清空搜索"
            >
              ✕
            </button>
          ) : null}
        </div>
        <div className="document-tree-actions">
          <button
            type="button"
            className="btn-create-folder"
            onClick={onCreateFolder}
            disabled={busy}
            title="新建项目分类文件夹"
          >
            + 📁 新建分类
          </button>
          {folders.length > 0 ? (
            <button
              type="button"
              className="btn-collapse-toggle"
              onClick={toggleAllCollapse}
              title={areAllCollapsed ? "展开全部文件夹" : "折叠全部文件夹"}
            >
              {areAllCollapsed ? "⊞ 展开" : "⊟ 折叠"}
            </button>
          ) : null}
        </div>
      </div>

      <div className="document-tree-list">
        {/* Render custom folders */}
        {filteredFolders.map((folder) => {
          const folderDocs = filterDocs(folderMap[folder.id] ?? []);
          const isCollapsed = !normalizedQuery && Boolean(collapsedFolderIds[folder.id]);

          return (
            <div key={folder.id} className="folder-group">
              <div
                className="folder-header"
                onClick={() => toggleFolderCollapse(folder.id)}
                title={`点击${isCollapsed ? "展开" : "折叠"}分类`}
              >
                <div className="folder-title">
                  <span className="folder-toggle-icon">{isCollapsed ? "▸" : "▾"}</span>
                  <span className="folder-icon">📁</span>
                  <strong className="folder-name">{folder.name}</strong>
                  <span className="folder-badge">{folderDocs.length}</span>
                </div>
                <div className="folder-quick-actions" onClick={(e) => e.stopPropagation()}>
                  <button
                    type="button"
                    className="folder-action-btn"
                    title="在此分类下新建图纸"
                    disabled={busy}
                    onClick={() => onCreateDocumentInFolder(folder.id)}
                  >
                    +
                  </button>
                  <button
                    type="button"
                    className="folder-action-btn"
                    title="重命名分类"
                    disabled={busy}
                    onClick={() => onRenameFolder(folder)}
                  >
                    ✎
                  </button>
                  <button
                    type="button"
                    className="folder-action-btn delete"
                    title="删除分类（图纸将转入未分类）"
                    disabled={busy}
                    onClick={() => onDeleteFolder(folder)}
                  >
                    🗑
                  </button>
                </div>
              </div>

              {!isCollapsed ? (
                <div className="folder-document-list">
                  {folderDocs.length === 0 ? (
                    <div className="folder-empty-hint">暂无图纸，点击 + 新建</div>
                  ) : (
                    folderDocs.map((doc) => (
                      <div key={doc.id} className="document-list-item">
                        <button
                          type="button"
                          data-document-id={doc.id}
                          className={`document-open${activeDocumentId === doc.id ? " active" : ""}`}
                          disabled={busy}
                          onClick={() => onOpenDocument(doc.id)}
                        >
                          <strong>{doc.name}</strong>
                          <span>{doc.element_count} 个元素 · r{doc.revision}</span>
                        </button>
                        <select
                          className="document-folder-move-select"
                          value={folder.id}
                          disabled={busy}
                          title="移动图纸到其他项目分类"
                          onChange={(e) => onMoveDocument(doc.id, e.target.value)}
                        >
                          <option value="" disabled>
                            📂 移动至…
                          </option>
                          <option value="">📁 未分类</option>
                          {folders.map((f) => (
                            <option key={f.id} value={f.id}>
                              📁 {f.name}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="document-delete"
                          data-testid="delete-document"
                          data-document-id={doc.id}
                          aria-label={`删除文档 ${doc.name}`}
                          title={`删除 ${doc.name}`}
                          disabled={busy}
                          onClick={() => onDeleteDocument(doc)}
                        >
                          删除
                        </button>
                      </div>
                    ))
                  )}
                </div>
              ) : null}
            </div>
          );
        })}

        {/* Render uncategorized folder / items */}
        {(() => {
          const uncategorized = filterDocs(uncategorizedDocs);
          if (uncategorized.length === 0 && folders.length > 0) return null;
          const isCollapsed = !normalizedQuery && Boolean(collapsedFolderIds["_uncategorized"]);

          return (
            <div className="folder-group uncategorized-group">
              {folders.length > 0 ? (
                <div
                  className="folder-header uncategorized-header"
                  onClick={() => toggleFolderCollapse("_uncategorized")}
                  title={`点击${isCollapsed ? "展开" : "折叠"}未分类图纸`}
                >
                  <div className="folder-title">
                    <span className="folder-toggle-icon">{isCollapsed ? "▸" : "▾"}</span>
                    <span className="folder-icon">📂</span>
                    <strong className="folder-name">未分类图纸</strong>
                    <span className="folder-badge">{uncategorized.length}</span>
                  </div>
                  <div className="folder-quick-actions" onClick={(e) => e.stopPropagation()}>
                    <button
                      type="button"
                      className="folder-action-btn"
                      title="新建未分类图纸"
                      disabled={busy}
                      onClick={() => onCreateDocumentInFolder(undefined)}
                    >
                      +
                    </button>
                  </div>
                </div>
              ) : null}

              {!isCollapsed || folders.length === 0 ? (
                <div className="folder-document-list">
                  {uncategorized.map((doc) => (
                    <div key={doc.id} className="document-list-item">
                      <button
                        type="button"
                        data-document-id={doc.id}
                        className={`document-open${activeDocumentId === doc.id ? " active" : ""}`}
                        disabled={busy}
                        onClick={() => onOpenDocument(doc.id)}
                      >
                        <strong>{doc.name}</strong>
                        <span>{doc.element_count} 个元素 · r{doc.revision}</span>
                      </button>
                      {folders.length > 0 ? (
                        <select
                          className="document-folder-move-select"
                          value=""
                          disabled={busy}
                          title="归类到项目分类文件夹"
                          onChange={(e) => onMoveDocument(doc.id, e.target.value)}
                        >
                          <option value="" disabled>
                            📂 归类到…
                          </option>
                          {folders.map((f) => (
                            <option key={f.id} value={f.id}>
                              📁 {f.name}
                            </option>
                          ))}
                        </select>
                      ) : null}
                      <button
                        type="button"
                        className="document-delete"
                        data-testid="delete-document"
                        data-document-id={doc.id}
                        aria-label={`删除文档 ${doc.name}`}
                        title={`删除 ${doc.name}`}
                        disabled={busy}
                        onClick={() => onDeleteDocument(doc)}
                      >
                        删除
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })()}
      </div>
    </div>
  );
}
