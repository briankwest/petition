/* Dossier pages (/iren, /childress-kiowa): mark citation markers that directly
 * follow another marker, so the CSS separator comma appears only between markers
 * that are genuinely adjacent — never across the prose between two citations. */
(function () {
  'use strict';
  document.querySelectorAll('.irenfile sup.c').forEach(function (sup) {
    var n = sup.previousSibling;
    while (n && n.nodeType === 3 && !n.nodeValue.trim()) n = n.previousSibling;
    if (n && n.nodeType === 1 && n.tagName === 'SUP' && n.classList.contains('c')) {
      sup.classList.add('sep');
    }
  });
})();
