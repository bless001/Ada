# sample_project/main.py

from services.payment import PaymentService


def calculate_total(items):
    total = 0
    for item in items:
        total += item.price
    return total


def checkout(cart):
    amount = calculate_total(cart.items)
    payment = PaymentService()
    payment.charge(amount)