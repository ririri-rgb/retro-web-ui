const form = document.querySelector('#item-form');
form.addEventListener('submit', (event) => {
  event.preventDefault();
  const name = new FormData(form).get('name');
  localStorage.setItem('last-item', String(name));
});
