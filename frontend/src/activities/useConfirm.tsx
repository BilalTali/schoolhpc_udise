import { useCallback, useState } from "react";
import type { ReactNode } from "react";
import { Modal } from "./Dialog";

interface ConfirmOptions {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  danger?: boolean;
}

/** const [confirmUi, confirm] = useConfirm(); ... if (await confirm({...})) doIt(); */
export function useConfirm(): [ReactNode, (o: ConfirmOptions) => Promise<boolean>] {
  const [state, setState] = useState<(ConfirmOptions & { resolve: (ok: boolean) => void }) | null>(null);
  const confirm = useCallback((o: ConfirmOptions) => new Promise<boolean>((resolve) => setState({ ...o, resolve })), []);
  const done = (ok: boolean) => {
    state?.resolve(ok);
    setState(null);
  };
  const ui = state && (
    <Modal role="alertdialog" title={state.title} onClose={() => done(false)}
           footer={<>
             <button type="button" className="btn btn-outline" onClick={() => done(false)} data-autofocus>Cancel</button>
             <button type="button" className={`btn ${state.danger ? "btn-danger" : "btn-primary"}`} onClick={() => done(true)}>
               {state.confirmLabel}
             </button>
           </>}>
      <div className="lib-confirm-text">{state.message}</div>
    </Modal>
  );
  return [ui, confirm];
}
