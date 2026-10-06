# 知答 · RAG 智能客服

## 启动

```bash
pip install -r requirements.txt
streamlit run app.py
```

数据会保存到 `outputs/data/knowledge_bases.json`。上传 Markdown 后会按标题和长度自动切分，并建立本地轻量向量索引。

## 部署到 Streamlit Community Cloud

将本目录中的 `app.py`、`requirements.txt` 和 `data/酒店智能客服标准问答库.md` 上传到 GitHub 仓库，在 Streamlit Community Cloud 创建应用，入口文件选择 `app.py`。部署成功后，将生成的 `https://...streamlit.app` 地址复制到 Notion 页面，输入 `/embed` 即可嵌入完整客服系统。
