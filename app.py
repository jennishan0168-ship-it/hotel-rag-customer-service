import json
import os
import re
import hashlib
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict

import streamlit as st

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_FILE = DATA_DIR / "knowledge_bases.json"


def load_db() -> Dict:
    if DB_FILE.exists():
        try:
            db = json.loads(DB_FILE.read_text(encoding="utf-8"))
            # 自动升级旧版整篇切分的数据，确保酒店问答库按单问单答重建。
            seed = DATA_DIR / "酒店智能客服标准问答库.md"
            old = db.get("knowledge_bases", [])
            if seed.exists() and old and old[0].get("name") == "酒店智能客服标准问答库":
                first = old[0].get("documents", [{}])[0].get("chunks", [{}])[0].get("text", "")
                if "**Q：" not in first:
                    raw = seed.read_text(encoding="utf-8")
                    chunks = split_markdown(raw)
                    old[0]["documents"] = [{"name": seed.name, "updated_at": datetime.now().isoformat(), "chunks": [{"text": c, "vector": vectorize(c)} for c in chunks]}]
                    save_db(db)
            return db
        except Exception:
            pass
    # 首次启动自动载入随项目提供的酒店标准问答库。
    seed = DATA_DIR / "酒店智能客服标准问答库.md"
    if seed.exists():
        raw = seed.read_text(encoding="utf-8")
        chunks = split_markdown(raw)
        db = {"knowledge_bases": [{
            "id": "hotel-default", "name": "酒店智能客服标准问答库",
            "created_at": datetime.now().isoformat(),
            "documents": [{"name": seed.name, "updated_at": datetime.now().isoformat(),
                           "chunks": [{"text": c, "vector": vectorize(c)} for c in chunks]}]
        }]}
        save_db(db)
        return db
    return {"knowledge_bases": []}


def save_db(db: Dict):
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]", text.lower())


def vectorize(text: str) -> Dict[str, float]:
    terms = tokenize(text)
    counts = {}
    for term in terms:
        counts[term] = counts.get(term, 0) + 1
    norm = sum(v * v for v in counts.values()) ** 0.5 or 1
    return {k: v / norm for k, v in counts.items()}


def similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
    return sum(v * b.get(k, 0) for k, v in a.items())


def split_markdown(text: str, size: int = 700, overlap: int = 100) -> List[str]:
    # 酒店问答库采用“Q：问题 + 后续答案”的结构，优先按问答对切分，
    # 避免把多个问题拼在同一个分片里，检索后可以只返回一条标准答案。
    qa_blocks = re.findall(r"(?ms)^\*\*Q：.*?\*\*.*?(?=^\*\*Q：|\Z)", text)
    if qa_blocks:
        return [re.sub(r"\n{3,}", "\n\n", block.strip()) for block in qa_blocks]
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    sections = re.split(r"(?=^#{1,6}\s)", text, flags=re.M)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= size:
            chunks.append(section)
        else:
            start = 0
            while start < len(section):
                end = min(start + size, len(section))
                chunk = section[start:end].strip()
                if chunk:
                    chunks.append(chunk)
                if end == len(section):
                    break
                start = max(end - overlap, start + 1)
    return chunks


def ingest(files, kb_name: str):
    db = load_db()
    kb = next((x for x in db["knowledge_bases"] if x["name"] == kb_name), None)
    if kb is None:
        kb = {"id": hashlib.md5(kb_name.encode()).hexdigest()[:8], "name": kb_name, "created_at": datetime.now().isoformat(), "documents": []}
        db["knowledge_bases"].append(kb)
    for file in files:
        raw = file.read().decode("utf-8", errors="ignore")
        chunks = split_markdown(raw)
        doc = {"name": file.name, "updated_at": datetime.now().isoformat(), "chunks": [{"text": c, "vector": vectorize(c)} for c in chunks]}
        kb["documents"] = [d for d in kb["documents"] if d["name"] != file.name]
        kb["documents"].append(doc)
    save_db(db)
    return len(files)


def retrieve(query: str, enabled: List[str], top_k: int = 5):
    qv = vectorize(query)
    rows = []
    for kb in load_db()["knowledge_bases"]:
        if kb["name"] not in enabled:
            continue
        for doc in kb["documents"]:
            for chunk in doc["chunks"]:
                score = similarity(qv, chunk["vector"])
                rows.append({"score": score, "text": chunk["text"], "kb": kb["name"], "doc": doc["name"]})
    return sorted(rows, key=lambda x: x["score"], reverse=True)[:top_k]


def answer(query: str, hits: List[Dict]) -> str:
    if not hits or hits[0]["score"] <= 0:
        return "我暂时没有在已启用的知识库中找到相关内容。请尝试换一种问法，或先在知识库管理中上传相关 Markdown 文档。"
    # 只返回最高相关的一条标准答案，不拼接其他无关召回结果。
    best = hits[0]["text"].strip()
    best = re.sub(r"^\*\*Q：.*?\*\*\s*", "", best, count=1, flags=re.S)
    return re.sub(r"\s+", " ", best).strip()


st.set_page_config(page_title="知答 · RAG 智能客服", page_icon="✦", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;700&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans','Noto Sans SC', sans-serif; }
.stApp { background: #f5f7fb; }
[data-testid="stSidebar"] { background: #101827; }
[data-testid="stSidebar"] * { color: #dce6f4 !important; }
.brand { font-size: 25px; font-weight: 700; color: #fff; letter-spacing: -1px; margin: 12px 0 28px; }
.brand span { color: #69d1b0; }
.hero { background: linear-gradient(135deg,#17253a 0%,#233d59 100%); border-radius: 18px; padding: 28px 32px; color: white; margin-bottom: 22px; }
.hero h1 { margin: 0 0 7px; font-size: 28px; letter-spacing: -1px; }
.hero p { margin: 0; color: #b9c9dc; }
.metric { background:white; border-radius:14px; padding:18px 20px; border:1px solid #e6ebf2; }
.metric .num { font-size:26px; font-weight:700; color:#17253a; }
.metric .label { color:#718096; font-size:13px; }
.source { background:#f7fafc; border-left:3px solid #69d1b0; padding:10px 13px; border-radius:0 8px 8px 0; margin:8px 0; font-size:13px; }
</style>""", unsafe_allow_html=True)

db = load_db()
total_docs = sum(len(k["documents"]) for k in db["knowledge_bases"])
total_chunks = sum(len(d["chunks"]) for k in db["knowledge_bases"] for d in k["documents"])

with st.sidebar:
    st.markdown('<div class="brand">知答<span>·</span> RAG</div>', unsafe_allow_html=True)
    page = st.radio("工作台", ["智能客服对话", "知识库管理"], label_visibility="collapsed")
    st.divider()
    st.caption("本地工作区")
    st.caption(f"{len(db['knowledge_bases'])} 个知识库 · {total_docs} 份文档")
    st.divider()
    st.caption("RAG 智能客服 · v0.1")

if page == "知识库管理":
    st.markdown('<div class="hero"><h1>知识库管理</h1><p>上传 Markdown 文档，自动切分、向量化并建立可检索索引。</p></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.markdown(f'<div class="metric"><div class="num">{len(db["knowledge_bases"])}</div><div class="label">知识库</div></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="metric"><div class="num">{total_docs}</div><div class="label">文档总数</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="metric"><div class="num">{total_chunks}</div><div class="label">向量分片</div></div>', unsafe_allow_html=True)
    st.write("")
    left, right = st.columns([1, 1.35])
    with left:
        st.subheader("新建 / 导入")
        name = st.text_input("知识库名称", placeholder="例如：售后服务手册")
        files = st.file_uploader("上传 Markdown 文档", type=["md", "markdown"], accept_multiple_files=True)
        if st.button("开始处理并入库", type="primary", use_container_width=True):
            if not name.strip():
                st.error("请先填写知识库名称")
            elif not files:
                st.error("请至少上传一个 Markdown 文件")
            else:
                count = ingest(files, name.strip())
                st.success(f"已处理 {count} 份文档，完成切分与向量化。")
                st.rerun()
        st.info("支持 .md / .markdown。当前使用本地轻量向量索引，适合原型和内网部署。")
    with right:
        st.subheader("已有知识库")
        if not db["knowledge_bases"]:
            st.empty()
            st.info("还没有知识库，上传第一份文档开始吧。")
        for kb in db["knowledge_bases"]:
            with st.container(border=True):
                a, b = st.columns([3, 1])
                a.markdown(f"**{kb['name']}**  \n<span style='color:#718096;font-size:13px'>{len(kb['documents'])} 份文档 · {sum(len(d['chunks']) for d in kb['documents'])} 个分片</span>", unsafe_allow_html=True)
                if b.button("删除", key=f"del_{kb['id']}"):
                    db["knowledge_bases"] = [x for x in db["knowledge_bases"] if x["id"] != kb["id"]]
                    save_db(db)
                    st.rerun()
                for doc in kb["documents"]:
                    st.caption(f"↳ {doc['name']} · {len(doc['chunks'])} 个分片")
else:
    st.markdown('<div class="hero"><h1>智能客服对话</h1><p>选择知识库，向你的专属客服提问。检索过程会实时展示。</p></div>', unsafe_allow_html=True)
    kb_names = [k["name"] for k in db["knowledge_bases"]]
    if "messages" not in st.session_state:
        st.session_state.messages = []
    with st.sidebar:
        st.subheader("启用知识库")
        enabled = st.multiselect("选择本次对话使用的知识库", kb_names, default=kb_names, label_visibility="collapsed")
        st.caption("回答只会参考已勾选的知识库")
        if st.button("清空对话", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    if not kb_names:
        st.info("请先在“知识库管理”页面上传 Markdown 文档。")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander(f"查看检索来源 · {len(msg['sources'])} 条"):
                    for src in msg["sources"]:
                        st.markdown(f'<div class="source"><b>{src["kb"]}</b> / {src["doc"]}<br>{src["text"][:240]}...</div>', unsafe_allow_html=True)
    query = st.chat_input("输入你的问题，例如：退货需要满足什么条件？")
    if query:
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)
        with st.chat_message("assistant"):
            status = st.status("正在调用知识库检索工具…", expanded=True)
            status.write(f"检索范围：{', '.join(enabled) if enabled else '未选择知识库'}")
            hits = retrieve(query, enabled)
            status.write(f"已召回 {len(hits)} 条内容，正在整理答案…")
            status.update(label="检索完成", state="complete", expanded=False)
            placeholder = st.empty()
            response = answer(query, hits)
            rendered = ""
            # 逐字输出，模拟真实模型的流式回答。
            for token in response:
                rendered += token
                placeholder.markdown(rendered)
                time.sleep(0.018)
            if hits:
                with st.expander(f"查看检索来源 · {len(hits)} 条"):
                    for src in hits:
                        st.markdown(f'<div class="source"><b>{src["kb"]}</b> / {src["doc"]}<br>{src["text"][:240]}...</div>', unsafe_allow_html=True)
        st.session_state.messages.append({"role": "assistant", "content": response, "sources": hits})
