import { redirect } from "next/navigation";

import { getSessionUser } from "@/lib/auth";
import { ChatWorkspace } from "@/components/chat-workspace";

export default async function ChatPage() {
  const session = await getSessionUser();

  if (!session) {
    redirect("/login");
  }

  return <ChatWorkspace userEmail={session.email} />;
}
