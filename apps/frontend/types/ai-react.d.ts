declare module "ai/react" {
  export interface Message {
    id: string;
    role: "user" | "assistant" | "system" | string;
    content: string;
    toolInvocations?: unknown;
  }

  export interface UseChatOptions {
    api?: string;
    maxSteps?: number;
  }

  export interface UseChatReturn {
    messages: Message[];
    input: string;
    isLoading: boolean;
    handleInputChange: (e: any) => void;
    handleSubmit: (e: any) => void;
  }

  export function useChat(options?: UseChatOptions): UseChatReturn;
}


