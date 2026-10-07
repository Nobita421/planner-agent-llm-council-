(define (problem bw-sussman)
  (:domain blocksworld)
  (:objects a b c)
  (:init
    (ontable a)
    (ontable b)
    (on c a)
    (clear b)
    (clear c)
    (handempty)
  )
  (:goal
    (and
      (on a b)
      (on b c)
    )
  )
)
