const revealItems = document.querySelectorAll(".reveal");

if ("IntersectionObserver" in window) {
  const revealObserver = new IntersectionObserver(
    (entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    },
    {
      threshold: 0.16,
      rootMargin: "0px 0px -40px 0px",
    },
  );

  revealItems.forEach((item) => revealObserver.observe(item));
} else {
  revealItems.forEach((item) => item.classList.add("is-visible"));
}

const kitchenNote = document.querySelector("[data-kitchen-note]");

if (kitchenNote) {
  const notes = [
    "Сьогодні пасує щось тепле, домашнє і з хрусткою скоринкою.",
    "Найкращий рецепт вечора: проста страва, гарна музика і спокійна кухня.",
    "Навіть маленький десерт виглядає святково, якщо подати його з настроєм.",
    "Кухня найкраще оживає тоді, коли рецепт хочеться повторити ще раз.",
  ];

  let currentIndex = 0;

  window.setInterval(() => {
    currentIndex = (currentIndex + 1) % notes.length;
    kitchenNote.textContent = notes[currentIndex];
  }, 4200);
}

const heartButtons = document.querySelectorAll("[data-burst='heart']");

heartButtons.forEach((button) => {
  button.addEventListener("click", (event) => {
    const form = button.closest("form");
    if (!form || button.dataset.submitting === "true") return;

    event.preventDefault();
    button.dataset.submitting = "true";
    button.classList.add("is-bursting");

    for (let index = 0; index < 7; index += 1) {
      const particle = document.createElement("span");
      particle.className = "heart-particle";
      particle.textContent = "❤";

      const spreadX = `${(Math.random() - 0.5) * 90}px`;
      const spreadY = `${-24 - Math.random() * 72}px`;
      particle.style.setProperty("--x", spreadX);
      particle.style.setProperty("--y", spreadY);
      particle.style.animationDelay = `${index * 0.03}s`;

      button.appendChild(particle);
      window.setTimeout(() => particle.remove(), 650);
    }

    window.setTimeout(() => {
      form.submit();
    }, 320);
  });
});

const manageMenus = document.querySelectorAll("[data-manage-menu]");

manageMenus.forEach((menu) => {
  const toggle = menu.querySelector("[data-manage-toggle]");
  if (!toggle) return;

  toggle.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();

    manageMenus.forEach((item) => {
      if (item !== menu) {
        item.classList.remove("is-open");
      }
    });

    menu.classList.toggle("is-open");
  });
});

document.addEventListener("click", (event) => {
  manageMenus.forEach((menu) => {
    if (!menu.contains(event.target)) {
      menu.classList.remove("is-open");
    }
  });
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  manageMenus.forEach((menu) => menu.classList.remove("is-open"));
});
