/** A grouped inset list: an optional heading, a rounded card of rows, an optional footnote. */
export function Group({ title, footer, children, actions, id }: { title?: React.ReactNode; footer?: React.ReactNode; children: React.ReactNode; actions?: React.ReactNode; id?: string }) {
  return (
    <section className="mb-6" id={id}>
      {(title || actions) && (
        <div className="mb-1.5 flex items-end justify-between gap-3 px-1">
          {title && <h3 className="text-[0.8rem] font-semibold text-muted">{title}</h3>}
          {actions && <div className="flex flex-wrap items-center gap-1.5">{actions}</div>}
        </div>
      )}
      <div className="overflow-hidden rounded-xl border border-line/80 bg-surface shadow-[0_1px_2px_rgb(23_32_51/0.04)] [&>*+*]:border-t [&>*+*]:border-line/70">{children}</div>
      {footer && <div className="mt-1.5 px-1 text-xs leading-relaxed text-muted">{footer}</div>}
    </section>
  );
}
