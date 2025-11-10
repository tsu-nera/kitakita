:set -XOverloadedStrings

import Sound.Tidal.Context

tidal <- startTidal (superdirtTarget {oLatency = 0.1, oAddress = "127.0.0.1", oPort = 57120}) (defaultConfig {cFrameTimespan = 1/20})

let p = streamReplace tidal
let hush = streamHush tidal
let setcps v = streamOnce tidal $ cps v
let d1 = p 1
let d2 = p 2
let d3 = p 3
let d4 = p 4
