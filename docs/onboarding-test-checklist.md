# Onboarding Manual QA Checklist

- User can skip onboarding and does not see it again on refresh or later login.
- User with Google Calendar connected sees the connected calendar state.
- User selections persist in the database through `/api/v1/onboarding/status`.
- Generated first prompt appears in the dashboard AI chat and is submitted once.
- Refreshing the dashboard does not resubmit the first prompt.
- If first prompt submission fails, the prompt remains in the chat input for manual sending.
- Logout and login does not show onboarding again after completion.
- Settings can reopen onboarding without forcing it on completed users.
- Mobile layout is usable across all seven steps.
