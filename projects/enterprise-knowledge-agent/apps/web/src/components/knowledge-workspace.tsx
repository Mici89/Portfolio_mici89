"use client";

import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import {
  askKnowledgeBase,
  createKnowledgeBase,
  deleteDocument,
  getDocuments,
  retryDocument,
  uploadDocument,
} from "@/lib/api";
import type {
  Document,
  KnowledgeBase,
  QuestionResponse,
} from "@/lib/api";

type View = "documents" | "chat";

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function KnowledgeWorkspace({
  initialKnowledgeBases,
  initialError = "",
}: {
  initialKnowledgeBases: KnowledgeBase[];
  initialError?: string;
}) {
  const [knowledgeBases, setKnowledgeBases] = useState(initialKnowledgeBases);
  const [selectedId, setSelectedId] = useState(initialKnowledgeBases[0]?.id ?? "");
  const [view, setView] = useState<View>("documents");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [notice, setNotice] = useState(initialError);
  const [createOpen, setCreateOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<QuestionResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selected = knowledgeBases.find((item) => item.id === selectedId);

  useEffect(() => {
    if (!selectedId) {
      return;
    }

    let active = true;

    getDocuments(selectedId)
      .then((items) => {
        if (active) setDocuments(items);
      })
      .catch((error: unknown) => {
        if (active) {
          setNotice(error instanceof Error ? error.message : "获取文档失败");
        }
      })
      .finally(() => {
        if (active) setLoadingDocuments(false);
      });

    return () => {
      active = false;
    };
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId || !documents.some((item) => item.status === "processing" || item.status === "parsing" || item.status === "chunking" || item.status === "embedding")) {
      return;
    }
    const timer = window.setInterval(() => {
      getDocuments(selectedId).then(setDocuments).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [selectedId, documents]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreating(true);
    setNotice("");

    try {
      const created = await createKnowledgeBase({
        name: createName.trim(),
        description: createDescription.trim() || undefined,
      });
      setKnowledgeBases((current) => [created, ...current]);
      setSelectedId(created.id);
      setCreateName("");
      setCreateDescription("");
      setCreateOpen(false);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "创建知识库失败");
    } finally {
      setCreating(false);
    }
  }

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !selectedId) return;

    setUploading(true);
    setNotice("");
    try {
      const uploaded = await uploadDocument(selectedId, file);
      setDocuments((current) => [uploaded, ...current]);
      setNotice(`“${file.name}”已进入处理队列`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "上传文档失败");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  async function handleDelete(document: Document) {
    if (!selectedId || !window.confirm(`确认删除“${document.file_name}”吗？`)) {
      return;
    }

    try {
      await deleteDocument(selectedId, document.id);
      setDocuments((current) => current.filter((item) => item.id !== document.id));
      setNotice("文档已删除");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "删除文档失败");
    }
  }

  async function handleRetry(document: Document) {
    if (!selectedId) return;
    try {
      const updated = await retryDocument(selectedId, document.id);
      setDocuments((current) => current.map((item) => item.id === updated.id ? updated : item));
      setNotice(`“${document.file_name}”已重新进入处理队列`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "重试文档处理失败");
    }
  }

  function documentStatusLabel(value: string) {
    return {
      processing: "排队中",
      parsing: "解析中",
      chunking: "切片中",
      embedding: "向量化中",
      ready: "已就绪",
      failed: "处理失败",
    }[value] ?? value;
  }

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId || !question.trim()) return;

    const submittedQuestion = question.trim();
    setAsking(true);
    setNotice("");
    try {
      const result = await askKnowledgeBase(selectedId, submittedQuestion);
      setAnswer(result);
      setQuestion("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "智能问答暂时不可用");
    } finally {
      setAsking(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#f5f7f8] text-slate-900">
      <div className="mx-auto flex min-h-screen max-w-[1500px]">
        <aside className="hidden w-72 shrink-0 border-r border-slate-200/80 bg-white px-5 py-6 lg:flex lg:flex-col">
          <div className="mb-9 flex items-center gap-3 px-2">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-[#173f35] text-lg font-bold text-white">
              K
            </div>
            <div>
              <p className="font-semibold tracking-tight">Knowledge OS</p>
              <p className="text-xs text-slate-400">企业智能知识中枢</p>
            </div>
          </div>

          <div className="mb-3 flex items-center justify-between px-2">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
              知识库
            </p>
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              aria-label="新建知识库"
              className="grid h-7 w-7 place-items-center rounded-lg text-lg text-slate-500 hover:bg-slate-100"
            >
              +
            </button>
          </div>

          <nav className="space-y-1.5">
            {knowledgeBases.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setSelectedId(item.id);
                  setAnswer(null);
                }}
                className={`w-full rounded-xl px-3 py-3 text-left transition ${
                  item.id === selectedId
                    ? "bg-[#e9f2ee] text-[#173f35]"
                    : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                <span className="block truncate text-sm font-medium">{item.name}</span>
                <span className="mt-1 block truncate text-xs opacity-60">
                  {item.description ?? "暂无描述"}
                </span>
              </button>
            ))}
          </nav>

          <div className="mt-auto rounded-2xl bg-[#173f35] p-4 text-white">
            <p className="text-sm font-medium">本地向量检索</p>
            <p className="mt-1 text-xs leading-5 text-white/60">
              BGE-M3 与 pgvector 已连接，问答由 DeepSeek 生成。
            </p>
          </div>
        </aside>

        <section className="min-w-0 flex-1 px-5 py-6 sm:px-8 lg:px-12 lg:py-10">
          <header className="mb-8 flex flex-wrap items-start justify-between gap-5">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[#47786b]">
                Enterprise Knowledge Agent
              </p>
              <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
                {selected?.name ?? "企业知识库"}
              </h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">
                {selected?.description ?? "创建一个知识库，开始沉淀和检索企业知识。"}
              </p>
            </div>

            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="rounded-xl bg-[#173f35] px-4 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-[#225849]"
            >
              ＋ 新建知识库
            </button>
          </header>

          {notice && (
            <div className="mb-6 flex items-center justify-between rounded-xl border border-[#cfe0da] bg-[#edf5f2] px-4 py-3 text-sm text-[#285c4e]">
              <span>{notice}</span>
              <button type="button" onClick={() => setNotice("")} aria-label="关闭提示">
                ×
              </button>
            </div>
          )}

          {selected ? (
            <>
              <div className="mb-6 flex border-b border-slate-200">
                {(["documents", "chat"] as View[]).map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setView(item)}
                    className={`relative px-5 py-3 text-sm font-medium ${
                      view === item ? "text-[#173f35]" : "text-slate-400"
                    }`}
                  >
                    {item === "documents" ? "文档管理" : "智能问答"}
                    {view === item && (
                      <span className="absolute inset-x-4 bottom-0 h-0.5 rounded-full bg-[#173f35]" />
                    )}
                  </button>
                ))}
              </div>

              {view === "documents" ? (
                <div className="grid gap-6 xl:grid-cols-[1fr_300px]">
                  <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
                    <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
                      <div>
                        <h2 className="font-semibold">已入库文档</h2>
                        <p className="mt-1 text-xs text-slate-400">共 {documents.length} 份文档</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploading}
                        className="rounded-xl bg-[#dca85f] px-4 py-2.5 text-sm font-medium text-[#382713] transition hover:bg-[#d39b4c] disabled:opacity-50"
                      >
                        {uploading ? "处理中..." : "上传文档"}
                      </button>
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".txt,.md,.pdf"
                        className="hidden"
                        onChange={handleUpload}
                      />
                    </div>

                    {loadingDocuments ? (
                      <div className="p-12 text-center text-sm text-slate-400">正在读取文档...</div>
                    ) : documents.length === 0 ? (
                      <div className="p-14 text-center">
                        <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-slate-100 text-2xl">↥</div>
                        <p className="font-medium">还没有文档</p>
                        <p className="mt-1 text-sm text-slate-400">上传 PDF、Markdown 或 TXT 文件开始构建知识库</p>
                      </div>
                    ) : (
                      <div className="divide-y divide-slate-100">
                        {documents.map((document) => (
                          <article key={document.id} className="flex items-center gap-4 px-6 py-4">
                            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[#eef3f1] text-xs font-bold uppercase text-[#47786b]">
                              {document.file_name.split(".").pop()?.slice(0, 3) ?? "DOC"}
                            </div>
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-sm font-medium">{document.file_name}</p>
                              <p className="mt-1 text-xs text-slate-400">
                                {formatBytes(document.file_size)} · {formatDate(document.created_at)}
                              </p>
                            </div>
                            <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${document.status === "failed" ? "bg-red-50 text-red-700" : document.status === "ready" ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`} title={document.error_message ?? undefined}>
                              {documentStatusLabel(document.status)}
                            </span>
                            {document.status === "failed" && (
                              <button type="button" onClick={() => handleRetry(document)} className="rounded-lg px-2 py-1 text-sm text-[#47786b] hover:bg-[#e9f2ee]">
                                重试
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => handleDelete(document)}
                              className="rounded-lg px-2 py-1 text-sm text-slate-400 hover:bg-red-50 hover:text-red-600"
                            >
                              删除
                            </button>
                          </article>
                        ))}
                      </div>
                    )}
                  </section>

                  <aside className="space-y-4">
                    <div className="rounded-2xl bg-[#173f35] p-6 text-white">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-white/50">知识状态</p>
                      <p className="mt-4 text-4xl font-semibold">{documents.length}</p>
                      <p className="mt-1 text-sm text-white/65">份可检索文档</p>
                      <div className="mt-6 h-1.5 overflow-hidden rounded-full bg-white/15">
                        <div className="h-full w-full rounded-full bg-[#dca85f]" />
                      </div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-white p-5 text-sm leading-6 text-slate-500">
                      <p className="font-medium text-slate-800">支持格式</p>
                      <p className="mt-2">PDF、Markdown、TXT，单个文件最大 10 MB。上传后会自动解析、脱敏、切片并向量化。</p>
                    </div>
                  </aside>
                </div>
              ) : (
                <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
                  <section className="flex min-h-[560px] flex-col rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <div className="mb-6">
                      <h2 className="font-semibold">向知识库提问</h2>
                      <p className="mt-1 text-sm text-slate-400">回答将严格基于已入库资料，并附带来源。</p>
                    </div>

                    <div className="flex-1">
                      {answer ? (
                        <div className="rounded-2xl bg-[#f1f5f3] p-6">
                          <p className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-[#47786b]">AI 回答</p>
                          <p className="whitespace-pre-wrap text-[15px] leading-7 text-slate-700">{answer.answer}</p>
                          <p className="mt-4 border-t border-[#d7e6df] pt-3 text-xs text-[#47786b]">
                            Agent：{answer.agent_trace.intent ?? "knowledge_lookup"} · {answer.agent_trace.steps} 步 · {answer.agent_trace.tools.join(" → ") || "未调用工具"}
                          </p>
                        </div>
                      ) : (
                        <div className="grid h-full min-h-72 place-items-center text-center">
                          <div>
                            <div className="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-2xl bg-[#e9f2ee] text-2xl">✦</div>
                            <p className="font-medium">从一个具体问题开始</p>
                            <p className="mt-2 text-sm text-slate-400">例如：员工每年有多少天年假？</p>
                          </div>
                        </div>
                      )}
                    </div>

                    <form onSubmit={handleAsk} className="mt-6 flex gap-3">
                      <input
                        value={question}
                        onChange={(event) => setQuestion(event.target.value)}
                        placeholder="输入关于当前知识库的问题..."
                        className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none transition focus:border-[#47786b] focus:bg-white"
                      />
                      <button
                        type="submit"
                        disabled={asking || !question.trim()}
                        className="rounded-xl bg-[#173f35] px-5 py-3 text-sm font-medium text-white disabled:opacity-50"
                      >
                        {asking ? "思考中..." : "发送"}
                      </button>
                    </form>
                  </section>

                  <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
                    <h2 className="font-semibold">引用来源</h2>
                    <p className="mt-1 text-xs text-slate-400">用于核对回答依据</p>
                    <div className="mt-5 space-y-3">
                      {answer?.sources.length ? (
                        answer.sources.map((source) => (
                          <article key={`${source.document_id}-${source.chunk_index}`} className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                            <div className="mb-2 flex items-center justify-between text-xs">
                              <span className="font-semibold text-[#47786b]">资料 {source.source_number}</span>
                              <span className="text-slate-400">相关度 {(source.similarity * 100).toFixed(0)}%</span>
                            </div>
                            <p className="line-clamp-6 text-xs leading-5 text-slate-500">{source.content}</p>
                          </article>
                        ))
                      ) : (
                        <p className="rounded-xl bg-slate-50 px-4 py-8 text-center text-sm text-slate-400">提问后将在这里显示引用片段</p>
                      )}
                    </div>
                  </aside>
                </div>
              )}
            </>
          ) : (
            <section className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-24 text-center">
              <p className="text-lg font-medium">还没有知识库</p>
              <p className="mt-2 text-sm text-slate-400">新建一个知识库，开始上传和检索企业资料。</p>
            </section>
          )}
        </section>
      </div>

      {createOpen && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 px-4 backdrop-blur-sm">
          <form onSubmit={handleCreate} className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
            <div className="mb-6 flex items-start justify-between">
              <div>
                <h2 className="text-xl font-semibold">新建知识库</h2>
                <p className="mt-1 text-sm text-slate-400">为一组相关企业资料建立独立空间。</p>
              </div>
              <button type="button" onClick={() => setCreateOpen(false)} className="text-xl text-slate-400">×</button>
            </div>
            <label className="block text-sm font-medium text-slate-700">
              名称
              <input
                autoFocus
                required
                maxLength={100}
                value={createName}
                onChange={(event) => setCreateName(event.target.value)}
                placeholder="例如：员工制度知识库"
                className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-[#47786b]"
              />
            </label>
            <label className="mt-4 block text-sm font-medium text-slate-700">
              描述
              <textarea
                rows={4}
                value={createDescription}
                onChange={(event) => setCreateDescription(event.target.value)}
                placeholder="简单描述这个知识库的用途"
                className="mt-2 w-full resize-none rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-[#47786b]"
              />
            </label>
            <div className="mt-6 flex justify-end gap-3">
              <button type="button" onClick={() => setCreateOpen(false)} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm">取消</button>
              <button type="submit" disabled={creating || !createName.trim()} className="rounded-xl bg-[#173f35] px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50">
                {creating ? "创建中..." : "创建知识库"}
              </button>
            </div>
          </form>
        </div>
      )}
    </main>
  );
}
