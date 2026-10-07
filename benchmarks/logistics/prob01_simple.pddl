(define (problem logistics-simple)
  (:domain logistics)
  (:objects
    p1 - package
    t1 - truck
    loc1 loc2 - location
    city1 - city
  )
  (:init
    (in-city loc1 city1)
    (in-city loc2 city1)
    (at t1 loc1)
    (at p1 loc1)
  )
  (:goal
    (at p1 loc2)
  )
)
