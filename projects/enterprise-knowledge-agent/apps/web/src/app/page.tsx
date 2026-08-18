import { KnowledgeWorkspace } from "@/components/knowledge-workspace";
import { getKnowledgeBases } from "@/lib/api";
import type { KnowledgeBase } from "@/lib/api";

export default async function Home() {
  let knowledgeBases: KnowledgeBase[] = [];
  let initialError = "";
  try {
    knowledgeBases = await getKnowledgeBases();
  } catch (error) {
    initialError = error instanceof Error ? error.message : "无法连接知识库服务";
  }

  return <KnowledgeWorkspace initialKnowledgeBases={knowledgeBases} initialError={initialError} />;
}
