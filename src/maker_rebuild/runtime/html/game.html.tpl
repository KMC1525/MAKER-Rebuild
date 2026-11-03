<!doctype html>
<html lang="{{LANG}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="generator" content="MAKER-Rebuild {{VERSION}}">
<title>{{TITLE}}</title>
<link rel="stylesheet" href="code/css/fonts.css">
<link rel="stylesheet" href="code/css/game.css">
<link rel="stylesheet" href="code/css/theme.css">
</head>
<body>
<div id="mr-root">
  <canvas id="mr-canvas" tabindex="0" aria-label="{{TITLE}}"></canvas>
  <div id="mr-loading">Carregando…</div>
  <div id="mr-error" hidden><h2>Erro no jogo</h2><pre></pre>
    <p>Abra o console do navegador (F12) para mais detalhes. Se o problema persistir, rode o jogo por um servidor local:
    <code>maker-rebuild serve .</code></p></div>
  <div id="mr-touch" aria-hidden="true">
    <div class="pad">
      <button data-mr-key="up">▲</button><button data-mr-key="left">◀</button>
      <button data-mr-key="right">▶</button><button data-mr-key="down">▼</button>
    </div>
    <div class="btns"><button data-mr-key="cancel">✕</button><button data-mr-key="ok">OK</button></div>
  </div>
</div>
{{SCRIPTS}}
<script>MR.boot();</script>
</body>
</html>
