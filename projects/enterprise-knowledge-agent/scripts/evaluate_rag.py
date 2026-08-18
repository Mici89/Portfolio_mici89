import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def post_json(url: str, body: dict) -> dict | list:
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--knowledge-base-id", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--include-answers", action="store_true")
    args = parser.parse_args()

    cases = json.loads((ROOT / "evaluation/eval_set.json").read_text(encoding="utf-8"))
    recall_hits = 0
    answer_hits = 0

    for case in cases:
        search_url = f"{args.base_url}/knowledge-bases/{args.knowledge_base_id}/search"
        results = post_json(search_url, {"query": case["question"], "limit": args.top_k})
        retrieved_text = "\n".join(item["content"] for item in results)
        recall_ok = any(term in retrieved_text for term in case["expected_terms"])
        recall_hits += recall_ok

        answer_ok = None
        answer = ""
        if args.include_answers:
            ask_url = f"{args.base_url}/knowledge-bases/{args.knowledge_base_id}/ask"
            response = post_json(ask_url, {"question": case["question"], "top_k": args.top_k})
            answer = response["answer"]
            # A case can provide formatting variants, e.g. "10 天" and "10天".
            answer_ok = any(keyword in answer for keyword in case["answer_keywords"])
            answer_hits += answer_ok

        print(json.dumps({
            "question": case["question"],
            "recall_at_k": recall_ok,
            "answer_accuracy": answer_ok,
            "answer": answer,
        }, ensure_ascii=False))

    print(f"Recall@{args.top_k}: {recall_hits / len(cases):.2%}")
    if args.include_answers:
        print(f"Answer Accuracy: {answer_hits / len(cases):.2%}")


if __name__ == "__main__":
    main()
