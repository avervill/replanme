import { redirect } from "next/navigation";

export default function LegacyAuthCallbackPage() {
  redirect("/dashboard");
}
