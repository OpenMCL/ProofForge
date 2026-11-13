const src = document.getElementById("src");
const preview = document.getElementById("preview");
const status = document.getElementById("status");
let timer = null;
function render() {
  preview.innerHTML = marked.parse(src.value);
  renderMathInElement(preview, {delimiters: [
    {left: "$$", right: "$$", display: true},
    {left: "$", right: "$", display: false}]});
}
async function save() {
  const resp = await fetch(`/problems/${src.dataset.pid}/autosave/`, {
    method: "POST", headers: {"Content-Type": "application/json",
      "X-CSRFToken": document.cookie.match(/csrftoken=([^;]+)/)?.[1] || ""},
    body: JSON.stringify({content: src.value})});
  status.textContent = resp.ok ? "已儲存 " : (resp.status === 409 ? "已鎖定" : "未儲存");
}
src.addEventListener("input", () => {
  render();
  clearTimeout(timer);
  timer = setTimeout(save, 1500);
});
render();
