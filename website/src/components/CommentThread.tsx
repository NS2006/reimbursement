import { useEffect, useId, useRef, useState, type FocusEvent, type FormEvent, type KeyboardEvent } from "react";
import { BlueAlert } from "./blue/Alert";
import { BlueAvatar } from "./blue/Avatar";
import { BlueBadge } from "./blue/Badge";
import { BlueButton } from "./blue/Button";
import { BlueModal } from "./blue/Modal";
import { BlueTextarea } from "./blue/Textarea";
import { useBlueToast } from "./blue/useBlueToast";
import { t } from "../app/i18n";
import type { ReimbursementComment } from "../types/reimbursement";
import { formatDateTime } from "../utils/format";
import "../styles/components/CommentThread.css";

interface CommentThreadProps {
  comments: ReimbursementComment[];
  /** The signed-in user: only their own comments can be edited and deleted (the backend checks it too). */
  currentUserEmail: string;
  // The page's backend calls. Each one updates the comments it gets back and rejects with an Error whose message
  // can be shown to the user. "gone": the comment was deleted in the meantime (and is no longer in the list).
  onAdd: (text: string) => Promise<void>;
  onEdit: (comment: ReimbursementComment, text: string) => Promise<"saved" | "gone">;
  onDelete: (comment: ReimbursementComment) => Promise<"deleted" | "gone">;
  maxLength?: number;
}

function messageOf(error: unknown): string {
  return error instanceof Error && error.message ? error.message : t("errors.generic");
}

function isCtrlEnter(event: KeyboardEvent) {
  return event.key === "Enter" && (event.ctrlKey || event.metaKey);
}

function cursorToEnd(event: FocusEvent<HTMLTextAreaElement>) {
  const { length } = event.currentTarget.value;
  event.currentTarget.setSelectionRange(length, length);
}

// Comments on a report, for any reimbursement type: the list, a form to add one, and for the user's own comments
// Edit (in place) and Delete (after a confirmation dialog). A toast confirms every change that worked; when one
// fails, the message shows where the user acted and what they typed is kept, so they can try again.
export function CommentThread({
  comments,
  currentUserEmail,
  onAdd,
  onEdit,
  onDelete,
  maxLength = 2000,
}: CommentThreadProps) {
  const toast = useBlueToast();
  const idPrefix = useId();
  const threadId = `${idPrefix}-thread`;
  const editButtonId = (comment: ReimbursementComment) => `${idPrefix}-edit-${comment.id}`;
  const isOwn = (comment: ReimbursementComment) => comment.user_email.toLowerCase() === currentUserEmail.toLowerCase();

  // Where the keyboard focus goes after the next render, e.g. back to "Edit" once the editor closes,
  // or to the thread when the focused comment was deleted.
  const focusNext = useRef<string | null>(null);
  useEffect(() => {
    if (!focusNext.current) return;
    document.getElementById(focusNext.current)?.focus();
    focusNext.current = null;
  });

  // A new comment
  const [draft, setDraft] = useState("");
  const [posting, setPosting] = useState(false);
  const [postError, setPostError] = useState<string | null>(null);

  // Editing one comment in place
  const [editing, setEditing] = useState<{ id: number; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // The comment in the delete confirmation dialog
  const [toDelete, setToDelete] = useState<ReimbursementComment | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function post(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || posting) return;
    setPosting(true);
    setPostError(null);
    try {
      await onAdd(text);
      setDraft("");
      toast.success(t("components:comments.posted"));
    } catch (error) {
      setPostError(messageOf(error));
    } finally {
      setPosting(false);
    }
  }

  function startEditing(comment: ReimbursementComment) {
    setEditing({ id: comment.id, text: comment.description });
    setEditError(null);
  }

  function stopEditing(comment: ReimbursementComment) {
    setEditing(null);
    setEditError(null);
    focusNext.current = editButtonId(comment);
  }

  async function saveEdit(comment: ReimbursementComment) {
    if (!editing || saving) return;
    const text = editing.text.trim();
    if (!text) return;
    if (text === comment.description) {
      stopEditing(comment); // nothing changed: not marked as edited
      return;
    }
    setSaving(true);
    setEditError(null);
    try {
      const result = await onEdit(comment, text);
      setEditing(null);
      if (result === "gone") {
        focusNext.current = threadId;
        toast.error(t("components:comments.notSaved"), t("components:comments.goneWhileEditing"));
      } else {
        focusNext.current = editButtonId(comment);
        toast.success(t("components:comments.updated"));
      }
    } catch (error) {
      setEditError(messageOf(error));
    } finally {
      setSaving(false);
    }
  }

  function askToDelete(comment: ReimbursementComment) {
    setToDelete(comment);
    setDeleteError(null);
  }

  function closeDeleteDialog() {
    if (!deleting) setToDelete(null);
  }

  async function confirmDelete() {
    if (!toDelete || deleting) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      const result = await onDelete(toDelete);
      if (editing?.id === toDelete.id) setEditing(null);
      setToDelete(null);
      focusNext.current = threadId; // its Edit and Delete buttons are gone
      if (result === "gone") {
        toast.info(t("components:comments.alreadyDeleted"), t("components:comments.deletedElsewhere"));
      } else {
        toast.success(t("components:comments.deleted"));
      }
    } catch (error) {
      setDeleteError(messageOf(error)); // shown in the dialog, which stays open to try again
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div id={threadId} className="comment-thread" tabIndex={-1}>
      {comments.length > 0 ? (
        <ul className="comment-thread__list">
          {comments.map((comment) => {
            const own = isOwn(comment);
            const edit = own && editing?.id === comment.id ? editing : null;
            const created = formatDateTime(comment.created_at);
            return (
              <li key={comment.id} className="comment-thread__item">
                <BlueAvatar name={comment.user_name} size="sm" />
                <div className="comment-thread__body">
                  <div className="comment-thread__header">
                    <p className="comment-thread__meta">
                      <strong>{comment.user_name}</strong>
                      {own ? <BlueBadge variant="info">{t("components:comments.you")}</BlueBadge> : null}
                      <span className="comment-thread__time">
                        <time dateTime={comment.created_at}>{created}</time>
                        {comment.edited_at ? (
                          <span className="comment-thread__edited">
                            {" "}
                            · {t("components:comments.edited")}{" "}
                            <time dateTime={comment.edited_at}>{formatDateTime(comment.edited_at)}</time>
                          </span>
                        ) : null}
                      </span>
                    </p>
                    {own && !edit ? (
                      <div className="comment-thread__actions">
                        <BlueButton
                          id={editButtonId(comment)}
                          variant="ghost"
                          size="sm"
                          aria-label={t("components:comments.editLabel", { time: created })}
                          onClick={() => startEditing(comment)}
                        >
                          {t("components:comments.edit")}
                        </BlueButton>
                        <BlueButton
                          variant="ghost"
                          size="sm"
                          className="comment-thread__delete"
                          aria-label={t("components:comments.deleteLabel", { time: created })}
                          onClick={() => askToDelete(comment)}
                        >
                          {t("components:comments.delete")}
                        </BlueButton>
                      </div>
                    ) : null}
                  </div>

                  {edit ? (
                    <div className="comment-thread__editor">
                      <BlueTextarea
                        aria-label={t("components:comments.editor")}
                        value={edit.text}
                        maxLength={maxLength}
                        readOnly={saving}
                        autoFocus
                        onFocus={cursorToEnd}
                        onChange={(event) => {
                          setEditing({ id: comment.id, text: event.target.value });
                          setEditError(null);
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Escape" && !saving) {
                            event.preventDefault();
                            stopEditing(comment);
                          } else if (isCtrlEnter(event)) {
                            event.preventDefault();
                            void saveEdit(comment);
                          }
                        }}
                        helperText={t("components:comments.editorHelp", { length: edit.text.length, max: maxLength })}
                      />
                      {editError ? (
                        <BlueAlert variant="error" title={t("components:comments.notSaved")}>
                          {editError}
                        </BlueAlert>
                      ) : null}
                      <div className="comment-thread__editor-actions">
                        <BlueButton
                          size="sm"
                          loading={saving}
                          disabled={!edit.text.trim() || edit.text.trim() === comment.description}
                          onClick={() => void saveEdit(comment)}
                        >
                          {t("components:comments.save")}
                        </BlueButton>
                        <BlueButton variant="secondary" size="sm" disabled={saving} onClick={() => stopEditing(comment)}>
                          {t("actions.cancel")}
                        </BlueButton>
                      </div>
                    </div>
                  ) : (
                    <p className="comment-thread__text">{comment.description}</p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="comment-thread__empty">{t("components:comments.empty")}</p>
      )}

      <form className="comment-thread__form" onSubmit={post}>
        <BlueTextarea
          label={t("components:comments.add")}
          placeholder={t("components:comments.placeholder")}
          value={draft}
          maxLength={maxLength}
          onChange={(event) => {
            setDraft(event.target.value);
            setPostError(null);
          }}
          onKeyDown={(event) => {
            if (isCtrlEnter(event)) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          helperText={t("components:comments.addHelp", { length: draft.length, max: maxLength })}
        />
        {postError ? (
          <BlueAlert variant="error" title={t("components:comments.notPosted")}>
            {postError}
          </BlueAlert>
        ) : null}
        <div>
          <BlueButton type="submit" loading={posting} disabled={!draft.trim()}>
            {t("components:comments.post")}
          </BlueButton>
        </div>
      </form>

      <BlueModal
        open={toDelete !== null}
        onClose={closeDeleteDialog}
        dismissible={!deleting}
        size="sm"
        title={t("components:comments.deleteTitle")}
        footer={
          <>
            <BlueButton variant="secondary" data-autofocus disabled={deleting} onClick={closeDeleteDialog}>
              {t("actions.cancel")}
            </BlueButton>
            <BlueButton variant="danger" loading={deleting} onClick={() => void confirmDelete()}>
              {t("components:comments.deleteConfirm")}
            </BlueButton>
          </>
        }
      >
        <p className="comment-thread__dialog-text">{t("components:comments.deleteText")}</p>
        {toDelete ? <blockquote className="comment-thread__quote">{toDelete.description}</blockquote> : null}
        {deleteError ? (
          <BlueAlert variant="error" title={t("components:comments.notDeleted")}>
            {deleteError}
          </BlueAlert>
        ) : null}
      </BlueModal>
    </div>
  );
}
