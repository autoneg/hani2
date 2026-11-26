import { useState } from "react";
import { createPortal } from "react-dom";
import { CircleHelp } from "lucide-react";
import { Modal } from "./Modal";

/** The dialog behind a `?` button (portalled to the body, so it is never clipped by a pane). */
export function HelpDialog({ title, onClose, children, wide = true }: { title: React.ReactNode; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return createPortal(
    <Modal open onClose={onClose} title={title} wide={wide}>
      {children}
    </Modal>,
    document.body,
  );
}

/** A small `?` button that opens a :func:`HelpDialog`; ``render`` builds the body only when it opens.
 *  Shared by the tools (``ToolHelp``) and the admin console's settings rows. */
export function HelpButton({ label, title, render, size = 15, className = "btn-ghost px-1.5 py-1", wide }: { label: string; title: React.ReactNode; render: () => React.ReactNode; size?: number; className?: string; wide?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)} aria-label={label} title={label} data-help-button>
        <CircleHelp size={size} />
      </button>
      {open && (
        <HelpDialog title={title} onClose={() => setOpen(false)} wide={wide}>
          {render()}
        </HelpDialog>
      )}
    </>
  );
}
