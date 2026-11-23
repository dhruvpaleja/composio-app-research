(function(){
  var rows=[].slice.call(document.querySelectorAll('tr.arow-main'));
  var q=document.getElementById('q'),fc=document.getElementById('fcat'),fv=document.getElementById('fver'),fa=document.getElementById('facc'),fp=document.getElementById('fcomp'),cnt=document.getElementById('count');
  function apply(){var t=(q.value||'').toLowerCase().trim(),n=0;
    rows.forEach(function(r){var ok=(!t||r.dataset.q.indexOf(t)>-1)&&(!fc.value||r.dataset.cat===fc.value)&&(!fv.value||r.dataset.verdict===fv.value)&&(!fa.value||r.dataset.access===fa.value)&&(!fp.checked||r.dataset.comp==='n');
      r.hidden=!ok;var d=r.nextElementSibling;if(!ok&&d)d.hidden=true;if(ok)n++;});
    cnt.textContent=n+(n===1?' app':' apps');}
  [q,fc,fv,fa,fp].forEach(function(el){el.addEventListener('input',apply);el.addEventListener('change',apply);});
  document.querySelectorAll('button.exp').forEach(function(b){b.addEventListener('click',function(){
    var d=document.getElementById(b.getAttribute('aria-controls'));var open=b.getAttribute('aria-expanded')==='true';
    b.setAttribute('aria-expanded',String(!open));d.hidden=open;});});
  function openHash(){var m=location.hash.match(/^#app-(\d+)$/);if(!m)return;var r=document.getElementById('app-'+m[1]);if(!r)return;
    [q,fc,fv,fa].forEach(function(e){e.value='';});fp.checked=false;apply();
    var b=r.querySelector('button.exp');if(b&&b.getAttribute('aria-expanded')!=='true')b.click();}
  window.addEventListener('hashchange',openHash);openHash();
})();
