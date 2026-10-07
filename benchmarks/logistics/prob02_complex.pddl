(define (problem logistics-multi-city)
  (:domain logistics)
  (:objects
    p1 p2 - package
    t1 t2 - truck
    a1 - airplane
    c1_loc1 c2_loc1 - location
    c1_apt c2_apt - airport
    c1 c2 - city
  )
  (:init
    (in-city c1_loc1 c1)
    (in-city c1_apt c1)
    (in-city c2_loc1 c2)
    (in-city c2_apt c2)
    (at t1 c1_loc1)
    (at t2 c2_loc1)
    (at a1 c1_apt)
    (at p1 c1_loc1)
    (at p2 c2_loc1)
  )
  (:goal
    (and
      (at p1 c2_loc1)
      (at p2 c1_loc1)
    )
  )
)
