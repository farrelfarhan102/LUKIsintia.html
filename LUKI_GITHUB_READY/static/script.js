// FilePoint interactions: click ripple on every button + reward category tabs
(function(){
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // 1) Ripple + press feedback on every button in the app
  document.addEventListener('click', function(e){
    var btn = e.target.closest('button, .btn');
    if(!btn) return;
    if(btn.disabled) return;

    if(!reduceMotion){
      var ripple = document.createElement('span');
      ripple.className = 'ripple';
      var rect = btn.getBoundingClientRect();
      var size = Math.max(rect.width, rect.height) * 2;
      ripple.style.width = ripple.style.height = size + 'px';
      ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
      ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
      btn.appendChild(ripple);
      ripple.addEventListener('animationend', function(){ ripple.remove(); });
    }

    btn.classList.add('pressed');
    setTimeout(function(){ btn.classList.remove('pressed'); }, 340);

    // Little celebration burst specifically for a redeem button being submitted
    if(btn.classList.contains('btn-redeem') && !reduceMotion){
      burst(btn);
    }
  }, true);

  function burst(btn){
    var rect = btn.getBoundingClientRect();
    var colors = ['#3f6ff0', '#f5b400', '#1f9d55', '#8b5cf6'];
    for(var i = 0; i < 10; i++){
      var p = document.createElement('span');
      p.className = 'confetti-bit';
      p.style.left = (rect.left + rect.width / 2) + 'px';
      p.style.top = (rect.top) + 'px';
      p.style.background = colors[i % colors.length];
      var angle = (Math.PI * 2 * i) / 10;
      var dist = 40 + Math.random() * 30;
      p.style.setProperty('--dx', (Math.cos(angle) * dist) + 'px');
      p.style.setProperty('--dy', (Math.sin(angle) * dist - 20) + 'px');
      document.body.appendChild(p);
      p.addEventListener('animationend', function(){ this.remove(); });
    }
  }

  // 2) Reward category tabs (client-side filter, no reload)
  var tabs = document.querySelectorAll('.tab');
  var cards = document.querySelectorAll('.reward-card');
  if(tabs.length){
    tabs.forEach(function(tab){
      tab.addEventListener('click', function(){
        tabs.forEach(function(t){ t.classList.remove('active'); });
        tab.classList.add('active');
        var target = tab.getAttribute('data-tab');
        cards.forEach(function(card, i){
          var show = target === 'all' || card.getAttribute('data-group') === target;
          card.style.display = show ? '' : 'none';
          if(show && !reduceMotion){
            card.style.animation = 'none';
            void card.offsetWidth;
            card.style.animation = 'cardIn .32s ease ' + (i % 8) * 0.02 + 's both';
          }
        });
      });
    });
  }

  // 3) Auto-dismiss flash alerts with a gentle slide-out
  document.querySelectorAll('.alert').forEach(function(a){
    setTimeout(function(){
      a.classList.add('alert-out');
      setTimeout(function(){ a.remove(); }, 400);
    }, 4200);
  });
})();
