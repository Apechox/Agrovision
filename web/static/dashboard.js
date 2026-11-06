// Dashboard de AgroVision. Calcula y dibuja los indicadores a partir de filas normalizadas.
// Los datos pueden venir de la sesión actual (lo que la página acaba de leer) o de un CSV
// exportado antes (formato Excel con ";" o formato de datos con ","). Todo se calcula en el
// navegador: el CSV cargado no se sube a ningún lado.
(function (global) {
  'use strict';

  // ---------- lectura y normalización ----------
  const quitarAcentos = (s) => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '');
  const clave = (s) => quitarAcentos(s).toLowerCase().replace(/[^a-z0-9]/g, '');
  // encabezado (en cualquiera de los dos formatos de CSV) -> campo interno
  const ALIAS = {
    fuente: 'fuente', id: 'id', tipo: 'tipo', anchomm: 'ancho_mm', pesog: 'peso_g', calibre: 'calibre', madurez: 'madurez',
    manchas: 'manchas', estadodelregistro: 'estado', estadoregistro: 'estado',
    estadodelcalibre: 'estado_calibre', estadocalibre: 'estado_calibre', sesion: 'sesion',
  };
  // El CSV del operador no trae el estado del registro (solo exporta registros definitivos);
  // si la columna falta, todas las filas se consideran definitivas.
  const REQUERIDAS = ['ancho_mm', 'calibre'];
  const PROVISIONAL = 'Provisional';

  function separador(texto) {
    const fin = texto.search(/\r?\n/);
    const cabecera = fin >= 0 ? texto.slice(0, fin) : texto;
    return cabecera.split(';').length > cabecera.split(',').length ? ';' : ',';
  }

  function tablaCSV(texto, sep) {  // lector con comillas; no depende de librerías
    const filas = []; let fila = [], celda = '', enComillas = false;
    for (let i = 0; i < texto.length; i++) {
      const c = texto[i];
      if (enComillas) {
        if (c === '"') { if (texto[i + 1] === '"') { celda += '"'; i++; } else enComillas = false; } else celda += c;
      } else if (c === '"') enComillas = true;
      else if (c === sep) { fila.push(celda); celda = ''; }
      else if (c === '\n') { fila.push(celda); filas.push(fila); fila = []; celda = ''; }
      else if (c !== '\r') celda += c;
    }
    if (celda !== '' || fila.length) { fila.push(celda); filas.push(fila); }
    return filas.filter((f) => f.some((c) => c.trim() !== ''));
  }

  const numero = (v) => {
    if (v === null || v === undefined || String(v).trim() === '') return null;
    const n = Number(String(v).trim().replace(',', '.'));
    return Number.isFinite(n) ? n : null;
  };

  function normalizar(o) {
    return {
      fuente: String(o.fuente || '').trim() || '(sin nombre)', id: o.id ?? '', tipo: String(o.tipo || '').trim(),
      ancho_mm: numero(o.ancho_mm), peso_g: numero(o.peso_g), calibre: String(o.calibre || '').trim(), madurez: String(o.madurez || '').trim(),
      manchas: String(o.manchas || '').trim(), estado: String(o.estado || '').trim(),
      estado_calibre: String(o.estado_calibre || '').trim(),
    };
  }

  function leerCSV(texto) {
    texto = String(texto).replace(/^﻿/, '');
    const tabla = tablaCSV(texto, separador(texto));
    if (tabla.length < 2) return { error: 'El archivo no tiene filas de datos.' };
    const campos = tabla[0].map((c) => ALIAS[clave(c)] || null);
    const faltan = REQUERIDAS.filter((k) => !campos.includes(k));
    if (faltan.length) return { error: `No parece un CSV de AgroVision: faltan las columnas ${faltan.join(', ')}.` };
    const filas = tabla.slice(1).map((f) => {
      const o = {}; campos.forEach((k, i) => { if (k) o[k] = (f[i] ?? '').trim(); });
      return normalizar(o);
    });
    return { filas };
  }

  const desdeSesion = (registro) => registro.map((r) => normalizar({ ...r, estado: r.estado_registro }));

  // ---------- cálculo ----------
  const base = (tipo) => String(tipo).split(' (')[0].trim();  // "Tomate (asumido, ...)" -> "Tomate"

  function estadistica(valores) {
    const n = valores.length;
    if (!n) return { n: 0 };
    const media = valores.reduce((a, b) => a + b, 0) / n;
    // varianza muestral (n - 1); con un solo dato no hay dispersión que medir y queda en 0
    const varianza = n > 1 ? valores.reduce((a, b) => a + (b - media) ** 2, 0) / (n - 1) : 0;
    return { n, media, min: Math.min(...valores), max: Math.max(...valores), varianza };
  }

  function contar(filas, campo) {
    const m = {};
    filas.forEach((f) => { if (f[campo]) m[f[campo]] = (m[f[campo]] || 0) + 1; });
    return m;
  }

  function resumenPorArchivo(filas) {
    const grupos = {};
    filas.forEach((f) => { (grupos[f.fuente] = grupos[f.fuente] || []).push(f); });
    return Object.entries(grupos).map(([fuente, fs]) => {
      const c = contar(fs, 'calibre'), pred = Object.entries(c).sort((a, b) => b[1] - a[1])[0];
      return { fuente, n: fs.length, ancho: estadistica(fs.map((f) => f.ancho_mm).filter((v) => v !== null)),
        peso: estadistica(fs.map((f) => f.peso_g).filter((v) => v !== null)), calibre: pred ? pred[0] : '—' };
    });
  }

  function calcular(filas, filtros) {
    const visibles = filas.filter((f) => (!filtros.archivo || f.fuente === filtros.archivo) &&
      (!filtros.fruto || base(f.tipo) === filtros.fruto));
    const definitivas = visibles.filter((f) => f.estado !== PROVISIONAL);  // M6: los provisionales no entran
    const anchos = definitivas.map((f) => f.ancho_mm).filter((v) => v !== null);
    const pesos = definitivas.map((f) => f.peso_g).filter((v) => v !== null);
    return {
      visibles, definitivas, provisionales: visibles.length - definitivas.length,
      ancho: estadistica(anchos), peso: estadistica(pesos),
      calibre: contar(definitivas, 'calibre'), madurez: contar(definitivas, 'madurez'),
      manchas: contar(definitivas, 'manchas'),
      porArchivo: resumenPorArchivo(definitivas),
      estimadas: definitivas.some((f) => /estimad/i.test(f.estado_calibre)),
    };
  }

  // ---------- dibujo ----------
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const f1 = (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(1).replace('.', ','));
  const ORDEN_CALIBRE = ['Grande', 'Mediano', 'Pequeño'];  // el más grande arriba y con el tono más intenso

  // Donut como en la sección 6.2.2 del documento. Paleta azul ordinal validada (claro y oscuro):
  // la categoría que el documento lista primero toma el tono más marcado. Los porcentajes van
  // sobre el arco si caben; la leyenda da nombre, porcentaje y cantidad (sirve de vista en tabla).
  const ORDEN_MADUREZ = ['Maduro', 'En transición', 'Verde'];
  const ORDEN_CALIDAD = ['Sin manchas detectadas', 'Sin manchas', 'Con manchas detectadas', 'Con manchas'];
  const NEUTRO = /^(no evaluable|no aplica|pendiente|sin dato|otros)/i;

  function donut(titulo, datos, vacio, orden) {
    const total = Object.values(datos).reduce((a, b) => a + b, 0);
    const R = 15.9155, GAP = 0.9;
    let arcos = '', leyenda = '', centro;
    if (!total) {
      arcos = `<circle cx="21" cy="21" r="${R}" fill="none" stroke="var(--borde)" stroke-width="6.5"/>`;
      centro = '<text x="21" y="22" class="don-l">Sin datos</text>';
      leyenda = `<p class="chico">${esc(vacio)}</p>`;
    } else {
      const claves = Object.keys(datos).sort((a, b) => {
        const ia = orden ? orden.indexOf(a) : -1, ib = orden ? orden.indexOf(b) : -1;
        return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || datos[b] - datos[a];
      });
      const colores = claves.filter((k) => !NEUTRO.test(k)), neutros = claves.filter((k) => NEUTRO.test(k));
      const partes = colores.slice(0, 4).map((k, i) => ({ k, n: datos[k], tono: i + 1 }));
      const otros = colores.slice(4).reduce((a, k) => a + datos[k], 0);
      neutros.forEach((k) => partes.push({ k, n: datos[k], tono: 'n' }));
      if (otros) partes.push({ k: 'Otros', n: otros, tono: 'n' });
      let acum = 0;
      partes.forEach((p) => {
        const pct = (p.n / total) * 100, largo = partes.length === 1 ? 100 : Math.max(pct - GAP, 0.01);
        const dato = `${esc(p.k)}: ${p.n} (${Math.round(pct)}%)`;
        arcos += `<circle cx="21" cy="21" r="${R}" fill="none" stroke="var(--d${p.tono})" stroke-width="6.5" ` +
          `stroke-dasharray="${largo} ${100 - largo}" stroke-dashoffset="${25 - acum}"><title>${dato}</title></circle>`;
        if (pct >= 8) {  // etiqueta dentro del arco solo si cabe; si no, queda en la leyenda
          const ang = ((acum + pct / 2) / 100) * 2 * Math.PI - Math.PI / 2;
          arcos += `<text x="${(21 + R * Math.cos(ang)).toFixed(2)}" y="${(21 + R * Math.sin(ang)).toFixed(2)}" ` +
            `class="don-p" style="fill:var(--dt${p.tono})">${Math.round(pct)}%</text>`;
        }
        acum += pct;
        leyenda += `<li><span class="don-pt" style="background:var(--d${p.tono})"></span><span class="don-nom">${esc(p.k)}</span>` +
          `<span class="don-val">${Math.round(pct)}% <small>(${p.n})</small></span></li>`;
      });
      centro = `<text x="21" y="20.6" class="don-n">${total}</text><text x="21" y="25.4" class="don-l">${total === 1 ? 'fruto' : 'frutos'}</text>`;
      leyenda = `<ul class="don-leyenda">${leyenda}</ul>`;
    }
    return `<div class="don-card"><h3>${esc(titulo)}</h3>` +
      `<svg viewBox="0 0 42 42" class="don" role="img" aria-label="${esc(titulo)}">${arcos}${centro}</svg>${leyenda}</div>`;
  }

  // Indicadores a la izquierda, bajo los donuts: totales arriba y el rango del ancho abajo.
  // Cada magnitud va en un bloque con su nombre y su unidad entre corchetes; dentro, bloques chicos con el resumen.
  function dibujarKpis(r) {
    const a = r.ancho, p = r.peso, archivos = new Set(r.definitivas.map((f) => f.fuente)).size;
    const k = (t, v) => `<div class="kpi"><b>${v}</b><span>${esc(t)}</span></div>`;
    const v = (e, campo) => (e.n ? f1(e[campo]) : '—');
    const bloque = (titulo, columnas, hijos, nota) =>
      `<section class="kpi-bloque"><h3>${esc(titulo)}</h3><div class="kpi-fila c${columnas}">${hijos}</div>` +
      `${nota ? `<p class="chico">${esc(nota)}</p>` : ''}</section>`;
    const sinPeso = p.n ? '' : 'Sin datos de peso: la estimación (A3.4) aún no está integrada.';
    return `<div class="kpi-fila c2">${k('Tomates totales', r.definitivas.length)}${k('Archivos', archivos)}</div>` +
      bloque('Ancho [mm]', 3, k('Mín.', v(a, 'min')) + k('Medio', v(a, 'media')) + k('Máx.', v(a, 'max'))) +
      bloque('Peso [g]', 3, k('Mín.', v(p, 'min')) + k('Medio', v(p, 'media')) + k('Máx.', v(p, 'max')), sinPeso) +
      bloque('Varianza [mm², g²]', 2, k('Ancho', v(a, 'varianza')) + k('Peso', v(p, 'varianza')),
        'Varianza muestral (n − 1).');
  }

  function dibujarTabla(filas) {
    if (!filas.length) return '';
    return '<div class="grafica"><h3>Resumen por archivo</h3><div class="tabla-caja"><table><thead><tr>' +
      '<th>Archivo</th><th>Tomates</th><th>Ancho medio [mm]</th><th>Peso medio [g]</th><th>Calibre predominante</th></tr></thead><tbody>' +
      filas.map((f) => `<tr><td>${esc(f.fuente)}</td><td>${f.n}</td><td>${f.ancho.n ? f1(f.ancho.media) : '—'}</td>` +
        `<td>${f.peso.n ? f1(f.peso.media) : '—'}</td><td>${esc(f.calibre)}</td></tr>`).join('') + '</tbody></table></div></div>';
  }

  // ---------- estado y eventos ----------
  const est = { origen: 'sesion', actual: [], csv: null, archivo: '', fruto: '' };
  const $ = (s) => document.querySelector(s);

  function llenar(select, opciones, valor, todos) {
    const html = (todos ? `<option value="">${todos}</option>` : '') +
      opciones.map((o) => `<option value="${esc(o)}">${esc(o)}</option>`).join('');
    if (select.dataset.firma !== html) { select.innerHTML = html; select.dataset.firma = html; }
    select.value = opciones.includes(valor) ? valor : (todos ? '' : (opciones[0] ?? ''));
  }

  function pintar() {
    if (!$('#vista-dash') || $('#vista-dash').hidden) return;
    const filas = est.origen === 'csv' ? (est.csv ? est.csv.filas : []) : est.actual;
    llenar($('#dash-f-archivo'), [...new Set(filas.map((f) => f.fuente))], est.archivo, 'Todos');
    const frutos = [...new Set(filas.map((f) => base(f.tipo)).filter(Boolean))];
    llenar($('#dash-f-fruto'), frutos, est.fruto, frutos.length > 1 ? 'Todos' : null);  // un solo fruto: "Fruto: Tomate"
    est.archivo = $('#dash-f-archivo').value; est.fruto = $('#dash-f-fruto').value;
    $('#dash-nombre').textContent = est.csv ? `CSV cargado: ${est.csv.nombre} (${est.csv.filas.length} filas)` : '';

    if (!filas.length) {
      $('#titulo-dash').textContent = est.origen === 'csv'
        ? 'Carga un CSV exportado desde AgroVision para ver sus gráficas.'
        : 'Todavía no hay registros: procesa archivos o carga un CSV.';
      $('#donas').innerHTML = ''; $('#dash-total').textContent = '';
      $('#dash-kpi').innerHTML = ''; $('#graficas').innerHTML = '';
      return;
    }
    const r = calcular(filas, { archivo: est.archivo, fruto: est.fruto });
    const origen = est.origen === 'csv' ? `CSV «${est.csv.nombre}»` : 'sesión actual';
    $('#titulo-dash').textContent = `Origen: ${origen} · Registros definitivos: ${r.definitivas.length} ` +
      `(provisionales excluidos: ${r.provisionales})` + (r.estimadas ? ' · Medidas estimadas: calibración pendiente de validar' : '');
    $('#donas').innerHTML =
      donut('Madurez Visual', r.madurez, 'Sin datos: módulo A3.1 pendiente', ORDEN_MADUREZ) +
      donut('Calidad Visual', r.manchas, 'Sin datos: módulo A3.2 pendiente', ORDEN_CALIDAD) +
      donut('Calibre Aparente', r.calibre, 'Sin datos', ORDEN_CALIBRE);
    $('#dash-total').textContent = `Total de frutos analizados: ${r.definitivas.length}`;
    $('#dash-kpi').innerHTML = dibujarKpis(r);
    $('#graficas').innerHTML =
      dibujarTabla(r.porArchivo);
  }

  async function cargar(archivo) {
    try {
      const r = leerCSV(await archivo.text());
      if (r.error) { if (global.aviso) global.aviso(r.error, false); return; }
      est.csv = { nombre: archivo.name, filas: r.filas }; est.origen = 'csv'; est.archivo = est.fruto = '';
      document.querySelector('input[name="dash-origen"][value="csv"]').checked = true;
      if (global.aviso) global.aviso(`CSV cargado: ${r.filas.length} filas`);
      pintar();
    } catch (e) { if (global.aviso) global.aviso('No se pudo leer el archivo.', false); }
  }

  function iniciar() {
    document.querySelectorAll('input[name="dash-origen"]').forEach((r) =>
      r.addEventListener('change', () => { est.origen = r.value; est.archivo = est.fruto = ''; pintar(); }));
    $('#dash-cargar').addEventListener('click', () => $('#dash-archivo').click());
    $('#dash-archivo').addEventListener('change', (e) => { const f = e.target.files[0]; e.target.value = ''; if (f) cargar(f); });
    $('#dash-f-archivo').addEventListener('change', (e) => { est.archivo = e.target.value; pintar(); });
    $('#dash-f-fruto').addEventListener('change', (e) => { est.fruto = e.target.value; pintar(); });
  }

  global.Dash = { iniciar, pintar, setSesion: (registro) => { est.actual = desdeSesion(registro); }, leerCSV, calcular };
  if (typeof module !== 'undefined') module.exports = global.Dash;
})(typeof window !== 'undefined' ? window : globalThis);
