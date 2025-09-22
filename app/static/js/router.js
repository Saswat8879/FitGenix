(function(){
  const main = document.getElementById('main-content');
  const header = document.getElementById('site-header');

  if(!main) return;

  const DASHBOARD1_HTML = `
    <section class="center-dashboard">
      <div class="center-card">
        <h1>Welcome to FitGenix</h1>
        <p class="lead muted">Choose where you want to go</p>

        <div class="center-options">
          <a class="big-btn" href="/meals" data-internal>Meal Logger</a>
          <a class="big-btn" href="/activities" data-internal>Activity Logger</a>
          <a class="big-btn" href="/leaderboard" data-internal>Lifestyle Leaderboard</a>
        </div>
      </div>
    </section>
  `;
  function setHeaderVisible(visible){
    if(!header) return;
    header.style.display = visible ? '' : 'none';
  }

  async function fetchPage(url, replace=false){
    try {
      const u = new URL(url, window.location.origin);
      url = u.pathname + (u.search || '');
    } catch(e) {
    }
    if(url === '/dashboard1' || url.endsWith('/dashboard1')){
      setHeaderVisible(false);
      main.classList.add('page-exit-active');
      setTimeout(()=>{
        main.innerHTML = DASHBOARD1_HTML;
        main.classList.remove('page-exit-active');
        main.classList.add('page-enter');
        requestAnimationFrame(()=> main.classList.add('page-enter-active'));
      }, 120);
      if(!replace) history.pushState({url}, '', '/dashboard1');
      return;
    }
    setHeaderVisible(true);
    try{
      const resp = await fetch(url, {headers:{'X-Requested-With':'XMLHttpRequest'}});
      if(!resp.ok){ window.location.href = url; return; }
      const text = await resp.text();
      const parser = new DOMParser();
      const doc = parser.parseFromString(text, 'text/html');
      const newMain = doc.getElementById('main-content') || doc.querySelector('main');
      if(newMain){
        main.classList.add('page-exit-active');
        setTimeout(()=>{
          main.innerHTML = newMain.innerHTML;
          main.classList.remove('page-exit-active');
          main.classList.add('page-enter');
          requestAnimationFrame(()=> main.classList.add('page-enter-active'));
          Array.from(main.querySelectorAll('script')).forEach(s=>{ try{ eval(s.textContent) } catch(e){ console.warn(e) } });
        }, 140);
        if(!replace) history.pushState({url}, '', url);
      } else {
        window.location.href = url;
      }
    }catch(err){
      console.error('router fetch error', err);
      window.location.href = url;
    }
  }

  document.addEventListener('click', function(e){
    const a = e.target.closest('a');
    if(!a) return;
    const href = a.getAttribute('href');
    if(!href) return;
    if(href.startsWith('http') || href.startsWith('mailto:') || a.target) return;
    if(a.hasAttribute('data-internal') || href.startsWith('/')){
      e.preventDefault();
      fetchPage(href);
    }
  }, true);
  window.addEventListener('popstate', (ev)=>{
    const url = (ev.state && ev.state.url) ? ev.state.url : window.location.pathname;
    fetchPage(url, true);
  });
  window.navigateTo = (u)=> fetchPage(u);
  if(window.location.pathname === '/dashboard1'){
    fetchPage('/dashboard1', true);
  }
})();
