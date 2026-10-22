import { useEffect, useState, type FormEvent } from "react";
import type { User } from "../types/user";
import { errorMessage, request } from "./api";

// Logic for the login page (pages/LoginPage.tsx) and for remembering who is signed in.
// Real sign-in will come from the Blibli gateway; until then the user is picked from a list.

// ---------------------------------------------------------------------------
// Backend calls
// ---------------------------------------------------------------------------

async function getUsers(signal?: AbortSignal): Promise<User[]> {
  const body = await request<{ users: User[] }>("/users", { signal });
  return body.users;
}

async function login(email: string): Promise<User> {
  const body = await request<{ user: User }>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  return body.user;
}

// ---------------------------------------------------------------------------
// Current user: remembered in localStorage so a page refresh keeps them signed in
// ---------------------------------------------------------------------------

const STORAGE_KEY = "reimbursement.currentUser";

function isUser(value: unknown): value is User {
  return (
    typeof value === "object" &&
    value !== null &&
    "email" in value &&
    typeof value.email === "string" &&
    "name" in value &&
    typeof value.name === "string"
  );
}

function loadUser(): User | null {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
    return isUser(value) ? value : null;
  } catch {
    return null;
  }
}

export function useCurrentUser() {
  const [user, setUser] = useState<User | null>(loadUser);

  function signIn(picked: User) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(picked));
    } catch {
      // Storage is blocked (e.g. private window): the user stays signed in until the tab reloads.
    }
    setUser(picked);
  }

  function signOut() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Nothing stored, nothing to clear.
    }
    setUser(null);
  }

  return { user, signIn, signOut };
}

// ---------------------------------------------------------------------------
// Login page: the user list, the picked user and the "Continue" action
// ---------------------------------------------------------------------------

export type UsersState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; users: User[] };

export type LoginController = ReturnType<typeof useLoginController>;

export function useLoginController(onSignIn: (user: User) => void) {
  const [users, setUsers] = useState<UsersState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getUsers(controller.signal)
      .then((list) => setUsers({ status: "ready", users: list }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setUsers({ status: "error", message: errorMessage(error) });
      });
    return () => controller.abort();
  }, [attempt]);

  function reloadUsers() {
    setUsers({ status: "loading" });
    setAttempt((count) => count + 1);
  }

  function selectEmail(value: string) {
    setEmail(value);
    setLoginError(null);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!email) return;
    setSubmitting(true);
    setLoginError(null);
    try {
      onSignIn(await login(email));
    } catch (error) {
      setLoginError(errorMessage(error));
      setSubmitting(false);
    }
  }

  return { users, reloadUsers, email, selectEmail, submitting, loginError, submit };
}
