import { useStore } from "../store";

export const toast = (message: string, level: "success" | "error" = "success") => useStore.getState().pushToast({ message, level });

export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copied");
  } catch {
    toast("Copy failed: select the text and copy it", "error");
  }
}
