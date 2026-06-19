import { useState } from "react";

interface Props {
  disabled: boolean;
  onSend: (content: string) => Promise<void> | void;
}

const MAX_LEN = 4000;

export function ChatInput({ disabled, onSend }: Props) {
  const [value, setValue] = useState("");

  const submit = async () => {
    const trimmed = value.trim();
    if (!trimmed || trimmed.length > MAX_LEN) {
      return;
    }
    await onSend(trimmed);
    setValue("");
  };

  return (
    <form
      className="chat-input"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
        placeholder={
          disabled
            ? "Đang chờ backend sẵn sàng..."
            : "Nhập lệnh (vd: Mở Notepad và gõ Hello from local AI agent.)"
        }
        rows={3}
        maxLength={MAX_LEN}
      />
      <button type="submit" disabled={disabled || !value.trim()}>
        Send
      </button>
    </form>
  );
}