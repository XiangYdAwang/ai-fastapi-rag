const serviceStatus = document.getElementById("service-status");
const fileInput = document.getElementById("file-input");
const uploadButton = document.getElementById("upload-button");
const uploadStatus = document.getElementById("upload-status");
const documentName = document.getElementById("document-name");
const chunkCount = document.getElementById("chunk-count");
const documentId = document.getElementById("document-id");
const questionInput = document.getElementById("question-input");
const onlyCurrentDocument = document.getElementById("only-current-document");
const askButton = document.getElementById("ask-button");
const chatStatus = document.getElementById("chat-status");
const answerBox = document.getElementById("answer-box");
const sourcesList = document.getElementById("sources-list");

let currentDocumentId = null;

function setStatus(element, message, type = "") {
  element.textContent = message;
  element.className = `status-line ${type}`.trim();
}

function setBusy(button, busy, text) {
  button.disabled = busy;
  button.textContent = busy ? text : button.dataset.label;
}

async function checkHealth() {
  try {
    const response = await fetch("/health");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    serviceStatus.textContent = "服务正常";
    serviceStatus.className = "status status-ok";
  } catch (error) {
    serviceStatus.textContent = "服务不可用";
    serviceStatus.className = "status status-error";
    console.error(error);
  }
}

async function uploadAndEmbed() {
  const file = fileInput.files[0];

  if (!file) {
    setStatus(uploadStatus, "请先选择文档", "error");
    return;
  }

  uploadButton.dataset.label ||= uploadButton.textContent;
  setBusy(uploadButton, true, "正在上传…");
  setStatus(uploadStatus, "正在上传并解析文档…");

  try {
    const formData = new FormData();
    formData.append("file", file);

    const uploadResponse = await fetch("/api/documents/upload", {
      method: "POST",
      body: formData,
    });

    if (!uploadResponse.ok) {
      throw new Error(await uploadResponse.text());
    }

    const upload = await uploadResponse.json();
    currentDocumentId = upload.id;

    documentName.textContent = upload.filename;
    chunkCount.textContent = upload.chunks_created;
    documentId.textContent = upload.id;
    setStatus(uploadStatus, "文档已解析，正在生成 Embedding…");

    const embedResponse = await fetch(
      `/api/documents/${upload.id}/embed`,
      { method: "POST" },
    );

    if (!embedResponse.ok) {
      throw new Error(await embedResponse.text());
    }

    const embed = await embedResponse.json();
    setStatus(
      uploadStatus,
      `向量化完成，共生成 ${embed.embedded_chunks} 个向量。`,
      "success",
    );
  } catch (error) {
    console.error(error);
    setStatus(uploadStatus, `上传失败：${error.message}`, "error");
  } finally {
    setBusy(uploadButton, false, "");
  }
}

function parseSseBlock(block) {
  let eventName = "message";
  const dataLines = [];

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (!dataLines.length) {
    return null;
  }

  return {
    eventName,
    data: JSON.parse(dataLines.join("\n")),
  };
}

function renderSources(sources) {
  sourcesList.replaceChildren();

  if (!sources.length) {
    const empty = document.createElement("p");
    empty.className = "source-preview";
    empty.textContent = "没有检索到可用来源。";
    sourcesList.appendChild(empty);
    return;
  }

  sources.forEach((source, index) => {
    const card = document.createElement("article");
    card.className = "source-card";

    const title = document.createElement("div");
    title.className = "source-title";

    const filename = document.createElement("span");
    filename.textContent = `[${index + 1}] ${source.filename} / chunk ${source.chunk_index}`;

    const score = document.createElement("span");
    score.className = "source-score";
    score.textContent = `score ${Number(source.score).toFixed(4)}`;

    title.append(filename, score);

    const preview = document.createElement("p");
    preview.className = "source-preview";
    preview.textContent = source.content.slice(0, 240);

    card.append(title, preview);
    sourcesList.appendChild(card);
  });
}

async function askQuestion() {
  const question = questionInput.value.trim();

  if (!question) {
    setStatus(chatStatus, "请输入问题", "error");
    return;
  }

  askButton.dataset.label ||= askButton.textContent;
  setBusy(askButton, true, "生成中…");
  setStatus(chatStatus, "正在检索并生成回答…");
  answerBox.textContent = "";
  sourcesList.replaceChildren();

  const payload = {
    query: question,
    top_k: 3,
  };

  if (onlyCurrentDocument.checked && currentDocumentId) {
    payload.document_id = currentDocumentId;
  }

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(await response.text());
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();

      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        const parsed = parseSseBlock(block);

        if (!parsed) {
          continue;
        }

        if (parsed.eventName === "sources") {
          renderSources(parsed.data.sources || []);
        } else if (parsed.eventName === "token") {
          answerBox.textContent += parsed.data.content || "";
        } else if (parsed.eventName === "done") {
          answerBox.textContent = parsed.data.answer || answerBox.textContent;
          setStatus(chatStatus, "回答完成", "success");
        } else if (parsed.eventName === "error") {
          throw new Error(parsed.data.detail || "流式生成失败");
        }
      }
    }
  } catch (error) {
    console.error(error);
    setStatus(chatStatus, `生成失败：${error.message}`, "error");
  } finally {
    setBusy(askButton, false, "");
  }
}

uploadButton.addEventListener("click", uploadAndEmbed);
askButton.addEventListener("click", askQuestion);
questionInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    askQuestion();
  }
});

checkHealth();