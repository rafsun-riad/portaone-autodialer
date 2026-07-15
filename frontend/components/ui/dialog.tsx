type DialogProps = {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  widthClassName?: string;
};

export function Dialog({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  widthClassName = "max-w-3xl",
}: DialogProps) {
  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4 py-6"
      onClick={onClose}
    >
      <div
        aria-modal="true"
        role="dialog"
        className={`w-full ${widthClassName} rounded-[2rem] border border-white/70 bg-white p-6 shadow-[0_35px_90px_rgba(15,23,42,0.2)]`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-2xl font-semibold text-slate-950">{title}</h3>
            {description ? (
              <p className="mt-2 text-sm leading-7 text-slate-600">
                {description}
              </p>
            ) : null}
          </div>
          <button
            className="rounded-full border border-slate-200 px-3 py-1 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-950"
            onClick={onClose}
            type="button"
          >
            Close
          </button>
        </div>
        <div className="mt-6">{children}</div>
        {footer ? (
          <div className="mt-6 flex flex-wrap justify-end gap-3">{footer}</div>
        ) : null}
      </div>
    </div>
  );
}
