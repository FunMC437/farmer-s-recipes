const note = document.querySelector("[data-note]");

if (note) {
  const lines = [
    "Якщо запускаєш проєкт через сервер, відкривай головний маршрут застосунку.",
    "У Flask-версії вже є українські тексти, анімація сердечка і фільтр коментарів.",
    "Старий демо-варіант прибрано, щоб у папці не плуталися дві різні версії сайту.",
  ];

  let index = 0;

  window.setInterval(() => {
    index = (index + 1) % lines.length;
    note.textContent = lines[index];
  }, 3200);
}
