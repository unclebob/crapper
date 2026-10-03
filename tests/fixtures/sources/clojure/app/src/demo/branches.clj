(ns demo.branches)

(defn no-body [])

(defn arithmetic [x]
  (+ x 1))

(defn if-form [x]
  (if x 1 0))

(defn if-not-form [x]
  (if-not x 1 0))

(defn if-let-form [x]
  (if-let [y x] y 0))

(defn when-form [x]
  (when x 1))

(defn when-first-form [x]
  (when-first [y x] y))

(defn and-form [x y]
  (and x y))

(defn or-form [x y]
  (or x y))

(defn loop-form [x]
  (loop [i 0] (recur (inc i))))

(defn discarded-form [x]
  #_(if x 1 0)
  (when x 1))

(defn cond-form [x]
  (cond
    (= x 1) :one
    :else :other))

(defn condp-form [x]
  (condp = x
    1 :one
    2 :two))

(defn case-form [x]
  (case x
    1 :one
    :other))

(defn cond-thread [x]
  (cond-> x
    (pos? x) inc
    (even? x) (* 2)))

(defn some-thread-first [x]
  (some-> x inc dec))

(defn some-thread-last [x]
  (some->> x (map inc) (filter pos?)))

(defn keywords-in-a-string [x]
  "if when cond and or"
  x)

(defn form-in-a-string [x]
  "(if true 1 0)"
  x)

(defn keywords-in-a-comment [x]
  ;; if when cond
  x)

(defn keywords-in-a-trailing-comment [x]
  (if x :yes :no) ; and or when cond
)

(defn map-literals-in-cond [cell]
  (let [contents (:contents cell)]
    (cond
      (pred-a? contents)
      {:type :army :mode :awake :owner (:owner contents) :aboard true}

      (pred-b? contents)
      {:type :fighter :mode :awake :owner (:owner contents) :fuel 20 :from-carrier true}

      (pred-c? contents) contents

      (pred-d? cell)
      {:type :fighter :mode :awake :owner :player :fuel 20 :from-airport true}

      :else nil)))

(defn empty-list []
  ())
