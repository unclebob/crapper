(defn alpha [x]
  (if x 1 0))

(def rules
  [{:pred (fn [v]
            (if v (when (pos? v) true) false))}])

(defmacro unless [test & body]
  `(if ~test nil (do ~@body)))

(defn omega [y]
  y)
