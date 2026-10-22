// The login page (pages/LoginPage.tsx) and the page shown for an unknown address (pages/NotFoundPage.tsx).

const login = {
  title: "Sign in",
  intro: "Choose the user you want to act as.",
  note: "Real sign-in will come from the Blibli gateway. This picker is for development only.",
  loadingUsers: "Loading users…",
  loadError: "Couldn't load the users",
  noUsers: {
    title: "No users yet",
    text: "Add users to the app_user table first (see backend/database/seeds/app_user.sql).",
  },
  user: "User",
  pickUser: "Select a user",
  continue: "Continue",
  notFound: {
    text: "The address may be mistyped, or the page no longer exists.",
    home: "Go to the home page",
  },
};

export default login;
