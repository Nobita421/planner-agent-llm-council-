(define (domain logistics)
  (:requirements :strips :typing)
  (:types
    package vehicle location city - object
    truck airplane - vehicle
    airport - location
  )

  (:predicates
    (at ?obj - object ?loc - location)
    (in ?p - package ?veh - vehicle)
    (in-city ?loc - location ?city - city)
  )

  (:action load-truck
    :parameters (?p - package ?t - truck ?l - location)
    :precondition (and (at ?t ?l) (at ?p ?l))
    :effect (and (not (at ?p ?l)) (in ?p ?t))
  )

  (:action unload-truck
    :parameters (?p - package ?t - truck ?l - location)
    :precondition (and (at ?t ?l) (in ?p ?t))
    :effect (and (not (in ?p ?t)) (at ?p ?l))
  )

  (:action drive-truck
    :parameters (?t - truck ?from - location ?to - location ?city - city)
    :precondition (and (at ?t ?from) (in-city ?from ?city) (in-city ?to ?city))
    :effect (and (not (at ?t ?from)) (at ?t ?to))
  )

  (:action load-airplane
    :parameters (?p - package ?a - airplane ?l - location)
    :precondition (and (at ?a ?l) (at ?p ?l))
    :effect (and (not (at ?p ?l)) (in ?p ?a))
  )

  (:action unload-airplane
    :parameters (?p - package ?a - airplane ?l - location)
    :precondition (and (at ?a ?l) (in ?p ?a))
    :effect (and (not (in ?p ?a)) (at ?p ?l))
  )

  (:action fly-airplane
    :parameters (?a - airplane ?from - airport ?to - airport)
    :precondition (at ?a ?from)
    :effect (and (not (at ?a ?from)) (at ?a ?to))
  )
)
