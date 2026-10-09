
'use strict';
const sitePage=document.body.dataset.page;
document.querySelectorAll('.site-links a').forEach(a=>{if(a.dataset.page===sitePage)a.setAttribute('aria-current','page');});
