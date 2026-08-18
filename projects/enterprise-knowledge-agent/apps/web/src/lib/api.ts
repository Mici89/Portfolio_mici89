const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export type KnowledgeBase = {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type Document = {
  id: string;
  knowledge_base_id: string;
  file_name: string;
  content_type: string;
  file_size: number;
  status: string;
  error_message: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
};

export type AnswerSource = {
  source_number: number;
  document_id: string;
  chunk_index: number;
  content: string;
  similarity: number;
};

export type QuestionResponse = {
  answer: string;
  sources: AnswerSource[];
  agent_trace: {
    intent: string | null;
    steps: number;
    tools: string[];
  };
};

async function readError(response: Response, fallback: string) {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail ?? fallback;
  } catch {
    return fallback;
  }
}

export async function getKnowledgeBases(): Promise<KnowledgeBase[]> {
  const response = await fetch(`${API_BASE_URL}/knowledge-bases`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(await readError(response, "获取知识库列表失败"));
  }

  return response.json() as Promise<KnowledgeBase[]>;
}

export async function createKnowledgeBase(input: {
  name: string;
  description?: string;
}): Promise<KnowledgeBase> {
  const response = await fetch(`${API_BASE_URL}/knowledge-bases`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });

  if (!response.ok) {
    throw new Error(await readError(response, "创建知识库失败"));
  }

  return response.json() as Promise<KnowledgeBase>;
}

export async function getDocuments(knowledgeBaseId: string): Promise<Document[]> {
  const response = await fetch(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/documents`,
    { cache: "no-store" },
  );

  if (!response.ok) {
    throw new Error(await readError(response, "获取文档列表失败"));
  }

  return response.json() as Promise<Document[]>;
}

export async function uploadDocument(
  knowledgeBaseId: string,
  file: File,
): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/documents`,
    { method: "POST", body: formData },
  );

  if (!response.ok) {
    throw new Error(await readError(response, "上传文档失败"));
  }

  return response.json() as Promise<Document>;
}

export async function deleteDocument(
  knowledgeBaseId: string,
  documentId: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/documents/${documentId}`,
    { method: "DELETE" },
  );

  if (!response.ok) {
    throw new Error(await readError(response, "删除文档失败"));
  }
}

export async function retryDocument(
  knowledgeBaseId: string,
  documentId: string,
): Promise<Document> {
  const response = await fetch(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/documents/${documentId}/retry`,
    { method: "POST" },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "重试文档处理失败"));
  }
  return response.json() as Promise<Document>;
}

export async function askKnowledgeBase(
  knowledgeBaseId: string,
  question: string,
): Promise<QuestionResponse> {
  const response = await fetch(
    `${API_BASE_URL}/knowledge-bases/${knowledgeBaseId}/ask`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, top_k: 5 }),
    },
  );

  if (!response.ok) {
    throw new Error(await readError(response, "智能问答暂时不可用"));
  }

  return response.json() as Promise<QuestionResponse>;
}
