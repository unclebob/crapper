(require '[clojure.edn :as edn])

(doseq [entry (:entries (edn/read-string (slurp *in*)))]
  (println (:namespace entry)
           (:name entry)
           (:complexity entry)
           (pr-str (:coverage entry))
           (pr-str (:crap entry))))
