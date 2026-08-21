import { useEffect, useRef, useState } from "react";
import "./agentStreamingViewer.css";

type Props = {
  thinking: string;
  content: string;
  isStreaming: boolean;
  onStop?: () => void;
};

export function AgentStreamingViewer({ thinking, content, isStreaming, onStop }: Props) {
  const [thinkingOpen, setThinkingOpen] = useState(true);
  const [contentOpen, setContentOpen] = useState(true);
  const thinkingEndRef = useRef<HTMLDivElement>(null);
  const contentEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isStreaming) {
      thinkingEndRef.current?.scrollIntoView({ behavior: "smooth" });
      contentEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [thinking, content, isStreaming]);

  if (!thinking && !content && !isStreaming) return null;

  return (
    <div className="agent-streaming-viewer">
      <div className="agent-streaming-header">
        <div className="agent-streaming-title">
          <span className="streaming-pulse-dot" data-active={isStreaming} />
          <strong>{isStreaming ? "AI Agent 正在实时思考与规划…" : "本次规划思考与生成记录"}</strong>
        </div>
        {isStreaming && onStop ? (
          <button type="button" className="agent-streaming-stop-btn" onClick={onStop}>
            🛑 停止
          </button>
        ) : null}
      </div>

      {thinking ? (
        <details className="agent-streaming-section thinking" open={thinkingOpen} onToggle={(e) => setThinkingOpen(e.currentTarget.open)}>
          <summary className="agent-streaming-summary">
            <span>🧠 思考过程 (Reasoning / CoT)</span>
            <span className="char-count">{thinking.length} 字符</span>
          </summary>
          <div className="agent-streaming-content thinking-text">
            <pre>{thinking}</pre>
            {isStreaming ? <span className="streaming-cursor" /> : null}
            <div ref={thinkingEndRef} />
          </div>
        </details>
      ) : isStreaming && !content ? (
        <div className="agent-streaming-empty-thinking">
          <span className="streaming-spinner" />
          <span>正在连接大模型推理流并等待首字输出…</span>
        </div>
      ) : isStreaming && content ? (
        <div className="agent-streaming-direct-notice">
          <span>💡 当前大模型直接输出规划指令</span>
        </div>
      ) : null}

      {content ? (
        <details className="agent-streaming-section content" open={contentOpen} onToggle={(e) => setContentOpen(e.currentTarget.open)}>
          <summary className="agent-streaming-summary">
            <span>📝 输出内容 (Drafting Output)</span>
            <span className="char-count">{content.length} 字符</span>
          </summary>
          <div className="agent-streaming-content code-text">
            <pre>{content}</pre>
            {isStreaming && !thinking ? <span className="streaming-cursor" /> : null}
            <div ref={contentEndRef} />
          </div>
        </details>
      ) : null}
    </div>
  );
}
