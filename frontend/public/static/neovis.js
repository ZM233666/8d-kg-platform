;(function () {
  if (window.NeoVis) {
    window.__neovisReady = Promise.resolve()
    return
  }

  function loadOne(src) {
    return new Promise(function (resolve, reject) {
      var script = document.createElement('script')
      script.src = src
      script.async = true
      script.onload = function () {
        resolve()
      }
      script.onerror = function () {
        reject(new Error('Failed to load script: ' + src))
      }
      document.head.appendChild(script)
    })
  }

  window.__neovisReady = loadOne('https://cdn.jsdelivr.net/npm/neovis.js@2.1.0/dist/neovis.js').catch(function () {
    return loadOne('https://unpkg.com/neovis.js@2.1.0/dist/neovis.js')
  })
})()
