document.addEventListener('DOMContentLoaded', ()=>{
  try{
    const chartPlaceholders = document.querySelectorAll('.chart-placeholder');
    chartPlaceholders.forEach(ph=>{
      const el = document.createElement('div');
      el.className = 'card';
      el.style.padding = '18px';
      el.innerHTML = '<h3>Snapshot</h3><p class="small muted">Charts load here.</p>';
      ph.appendChild(el);
    });
  }catch(e){
    console.warn('dashboard init error', e);
  }
});
