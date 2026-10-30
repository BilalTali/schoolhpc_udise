import { AlertCircle, CheckCircle2 } from "lucide-react";

// What the pre-check found before the class check: every empty required answer, grouped by where it is filled,
// each question with its students (grade, section, name, ID), so they can be fixed first.

export interface PrecheckStudent { student_id: string; student_name: string; grade: string; section: string }
export interface PrecheckItem { where: string; part: string; question: string; students: PrecheckStudent[] }
export interface PrecheckResult { stage: string; students: number; complete: number; items: PrecheckItem[] }

export function PrecheckView({ result, onStart, onClose, starting }: {
  result: PrecheckResult;
  onStart: () => void;
  onClose: () => void;
  starting?: boolean;
}) {
  const places = [...new Set(result.items.map((i) => i.where))];
  const missing = result.items.reduce((n, i) => n + i.students.length, 0);
  return (
    <div className={`alert-box ${result.items.length ? "alert-warning" : "alert-success"} lib-inline-alert pc-box`}
         role="region" aria-label={`${result.stage}: before the check`}>
      {result.items.length ? <AlertCircle size={18} aria-hidden="true" /> : <CheckCircle2 size={18} aria-hidden="true" />}
      <div className="pc-body">
        <b>{result.stage}: {result.complete} of {result.students} students have every required answer.</b>
        {result.items.length > 0 && <> {missing} answer{missing === 1 ? " is" : "s are"} empty - fix them first, or start the check anyway.</>}
        {places.map((where) => (
          <div key={where} className="pc-place">
            <div className="pc-where">{where}</div>
            <ul>
              {result.items.filter((i) => i.where === where).map((i) => (
                <li key={`${i.part}|${i.question}`}>
                  <details>
                    <summary>{i.part} / <b>{i.question}</b> - {i.students.length} student{i.students.length === 1 ? "" : "s"}</summary>
                    <ul className="pc-students">
                      {i.students.map((s) => (
                        <li key={s.student_id}>{[s.grade, s.section && `Sec ${s.section}`].filter(Boolean).join(" ")} - {s.student_name} (ID {s.student_id})</li>
                      ))}
                    </ul>
                  </details>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div className="pc-actions">
          <button type="button" className="btn btn-primary btn-sm" onClick={onStart} disabled={starting}>
            {result.items.length ? "Start the check anyway" : "Start the check"}
          </button>
          <button type="button" className="btn btn-outline btn-sm" onClick={onClose}>{result.items.length ? "Close and fix first" : "Close"}</button>
        </div>
      </div>
    </div>
  );
}
