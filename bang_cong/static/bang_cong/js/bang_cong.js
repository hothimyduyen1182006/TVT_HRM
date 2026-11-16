(() => {
  const clock = document.querySelector('[data-clock]');
  const timeZone = 'Asia/Ho_Chi_Minh';
  const pad = value => String(value).padStart(2, '0');
  const currentTime = () => Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone, hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
  }).formatToParts(new Date()).filter(part => part.type !== 'literal').map(part => [part.type, Number(part.value)]));
  const updateClock = () => {
    const time = currentTime();
    if (clock) clock.textContent = `${pad(time.hour)}:${pad(time.minute)}:${pad(time.second)}`;
  };
  updateClock();
  window.setInterval(updateClock, 1000);
})();