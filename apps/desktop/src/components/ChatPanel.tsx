import { ChatInput } from "./ChatInput";
import { MessageList } from "./MessageList";
import type { ChatMessage, ToolCallLog } from "../state/sessionStore";

interface Props {
  messages: ChatMessage[];
  toolCalls: ToolCallLog[];
  disabled: boolean;
  onSend: (content: string) => Promise<void> | void;
}

export function ChatPanel({ messages, toolCalls, disabled, onSend }: Props) {
  return (
    <section className="panel chat-panel">
      <header>
        <h2>Chat</h2>
      </header>
      <MessageList messages={messages} toolCalls={toolCalls} />
      <ChatInput disabled={disabled} onSend={onSend} />
    </section>
  );
}