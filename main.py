"""Metro Renegade - an original Python/Pygame urban sandbox prototype.

The game is intentionally not a clone of any commercial title. It uses only
procedural shapes and text to evoke a polished open-world HUD and city vibe.
There is no prone mechanic.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterable

import pygame

WIDTH, HEIGHT = 1280, 720
FPS = 60
WORLD_W, WORLD_H = 3200, 2400
ROAD_W = 170
BLOCK = 520
LANE = (42, 44, 47)
SIDEWALK = (207, 201, 190)
ASPHALT = (63, 64, 66)
GRASS = (71, 124, 66)
WHITE = (245, 245, 238)
YELLOW = (232, 202, 71)
GREEN = (42, 210, 80)
RED = (225, 60, 52)
BLUE = (69, 155, 239)
BLACK = (8, 10, 14)
ORANGE = (255, 161, 65)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def vec_from_angle(angle: float) -> pygame.Vector2:
    return pygame.Vector2(math.cos(angle), math.sin(angle))


@dataclass
class Vehicle:
    pos: pygame.Vector2
    color: tuple[int, int, int]
    name: str
    speed: float = 0.0
    angle: float = 0.0
    kind: str = "car"

    @property
    def size(self) -> tuple[int, int]:
        return (64, 34) if self.kind == "car" else (48, 20)

    def update(self, dt: float, keys: pygame.key.ScancodeWrapper, player_driving: bool) -> None:
        if not player_driving:
            return
        accel = 640 if keys[pygame.K_w] or keys[pygame.K_UP] else 0
        reverse = 360 if keys[pygame.K_s] or keys[pygame.K_DOWN] else 0
        self.speed += (accel - reverse) * dt
        friction = 1.9 if keys[pygame.K_LSHIFT] else 1.15
        self.speed -= self.speed * friction * dt
        self.speed = clamp(self.speed, -220, 620)
        turn = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            turn -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            turn += 1
        turn_strength = 2.6 * (0.2 + min(abs(self.speed) / 320, 1.0))
        self.angle += turn * turn_strength * dt * (1 if self.speed >= 0 else -1)
        self.pos += vec_from_angle(self.angle) * self.speed * dt
        self.pos.x = clamp(self.pos.x, 40, WORLD_W - 40)
        self.pos.y = clamp(self.pos.y, 40, WORLD_H - 40)

    def draw(self, surface: pygame.Surface, camera: pygame.Vector2, selected: bool = False) -> None:
        w, h = self.size
        car = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rounded_rect(car, self.color, (0, 0, w, h), 9)
        pygame.draw.rounded_rect(car, (25, 29, 34), (w * 0.28, 5, w * 0.36, h - 10), 5)
        pygame.draw.rect(car, (235, 236, 210), (w - 8, 6, 5, 8))
        pygame.draw.rect(car, (190, 20, 25), (2, 6, 5, 8))
        if self.kind == "bike":
            pygame.draw.circle(car, BLACK, (8, h // 2), 7)
            pygame.draw.circle(car, BLACK, (w - 8, h // 2), 7)
        rotated = pygame.transform.rotate(car, -math.degrees(self.angle))
        rect = rotated.get_rect(center=self.pos - camera)
        surface.blit(rotated, rect)
        if selected:
            pygame.draw.circle(surface, YELLOW, self.pos - camera, 46, 2)


@dataclass
class Pedestrian:
    pos: pygame.Vector2
    color: tuple[int, int, int]
    direction: pygame.Vector2 = field(default_factory=lambda: pygame.Vector2(1, 0))
    timer: float = 0.0

    def update(self, dt: float) -> None:
        self.timer -= dt
        if self.timer <= 0:
            self.direction = pygame.Vector2(random.uniform(-1, 1), random.uniform(-1, 1))
            if self.direction.length_squared() == 0:
                self.direction = pygame.Vector2(1, 0)
            self.direction.normalize_ip()
            self.timer = random.uniform(1.0, 3.4)
        self.pos += self.direction * 42 * dt
        self.pos.x = clamp(self.pos.x, 60, WORLD_W - 60)
        self.pos.y = clamp(self.pos.y, 60, WORLD_H - 60)

    def draw(self, surface: pygame.Surface, camera: pygame.Vector2) -> None:
        p = self.pos - camera
        pygame.draw.circle(surface, self.color, p, 7)
        pygame.draw.line(surface, (35, 35, 38), (p.x, p.y + 7), (p.x, p.y + 18), 3)


@dataclass
class Mission:
    title: str
    detail: str
    pos: pygame.Vector2
    target: pygame.Vector2
    reward: int
    active: bool = False
    complete: bool = False


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Metro Renegade - Python Open World")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 20, bold=True)
        self.small = pygame.font.SysFont("arial", 15)
        self.big = pygame.font.SysFont("arial", 34, bold=True)
        self.player = pygame.Vector2(760, 720)
        self.player_angle = 0.0
        self.in_vehicle: Vehicle | None = None
        self.cash = 3285
        self.ammo = 220
        self.mag = 30
        self.time_minutes = 12 * 60 + 45
        self.show_help = True
        self.paused = False
        self.radio = 0
        self.message = "Press E near a vehicle. Press F at markers. No prone mechanic."
        self.message_timer = 6.0
        self.vehicles = [
            Vehicle(pygame.Vector2(850, 720), (24, 31, 40), "Shadow Sedan"),
            Vehicle(pygame.Vector2(1220, 1080), (215, 46, 34), "Crimson Cabrio"),
            Vehicle(pygame.Vector2(1740, 710), (245, 245, 238), "Pearl Sport"),
            Vehicle(pygame.Vector2(1820, 780), (35, 116, 230), "Azure Coupe"),
            Vehicle(pygame.Vector2(1660, 820), (95, 210, 53), "Lime Bike", kind="bike"),
        ]
        self.peds = [Pedestrian(pygame.Vector2(random.randrange(80, WORLD_W - 80), random.randrange(80, WORLD_H - 80)), random.choice([(230, 190, 145), (110, 80, 55), (245, 220, 170)])) for _ in range(70)]
        self.missions = [Mission("REPOSSESSION", "Recover the pearl sport car", pygame.Vector2(640, 940), pygame.Vector2(1740, 710), 850)]
        self.targets = [pygame.Vector2(520 + i * 95, 1540 + (i % 2) * 55) for i in range(8)]

    def camera(self) -> pygame.Vector2:
        focus = self.in_vehicle.pos if self.in_vehicle else self.player
        return pygame.Vector2(clamp(focus.x - WIDTH / 2, 0, WORLD_W - WIDTH), clamp(focus.y - HEIGHT / 2, 0, WORLD_H - HEIGHT))

    def update(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        if self.paused:
            return
        self.time_minutes = (self.time_minutes + dt * 1.8) % (24 * 60)
        if self.message_timer > 0:
            self.message_timer -= dt
        if self.in_vehicle:
            self.in_vehicle.update(dt, keys, True)
            self.player = self.in_vehicle.pos - vec_from_angle(self.in_vehicle.angle) * 28
        else:
            move = pygame.Vector2((keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT]), (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP]))
            if move.length_squared():
                move.normalize_ip()
                self.player_angle = math.atan2(move.y, move.x)
            self.player += move * (230 if keys[pygame.K_LSHIFT] else 145) * dt
            self.player.x = clamp(self.player.x, 35, WORLD_W - 35)
            self.player.y = clamp(self.player.y, 35, WORLD_H - 35)
        for ped in self.peds:
            ped.update(dt)
        for mission in self.missions:
            if mission.active and not mission.complete and self.player.distance_to(mission.target) < 70:
                mission.complete = True
                mission.active = False
                self.cash += mission.reward
                self.message = f"Mission passed: {mission.title} +${mission.reward}"
                self.message_timer = 5

    def nearest_vehicle(self) -> Vehicle | None:
        pos = self.in_vehicle.pos if self.in_vehicle else self.player
        near = min(self.vehicles, key=lambda v: v.pos.distance_to(pos))
        return near if near.pos.distance_to(pos) < 92 else None

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.paused = not self.paused
            elif event.key == pygame.K_h:
                self.show_help = not self.show_help
            elif event.key == pygame.K_TAB:
                self.radio = (self.radio + 1) % 4
                self.message = ["Radio: Downtown Pulse", "Radio: Coastline Funk", "Radio: Night Drive", "Radio off"][self.radio]
                self.message_timer = 3
            elif event.key == pygame.K_e:
                if self.in_vehicle:
                    self.player = self.in_vehicle.pos + pygame.Vector2(48, 0).rotate_rad(self.in_vehicle.angle)
                    self.message = f"Exited {self.in_vehicle.name}"
                    self.in_vehicle = None
                else:
                    vehicle = self.nearest_vehicle()
                    if vehicle:
                        self.in_vehicle = vehicle
                        self.message = f"Driving {vehicle.name}"
                    else:
                        self.message = "No vehicle close enough"
                self.message_timer = 3
            elif event.key == pygame.K_f:
                self.interact()
            elif event.key == pygame.K_r:
                self.mag = min(30, self.ammo)
                self.message = "Reloaded"
                self.message_timer = 2
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.shoot()
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            self.shoot()
        return True

    def interact(self) -> None:
        for mission in self.missions:
            if not mission.complete and self.player.distance_to(mission.pos) < 95:
                mission.active = True
                self.message = f"Mission started: {mission.title}"
                self.message_timer = 4
                return
        if self.player.distance_to(pygame.Vector2(1740, 760)) < 180:
            self.cash = max(0, self.cash - 50)
            self.message = "Garage tuned your ride for $50"
            self.message_timer = 3
        else:
            self.message = "Nothing to interact with here"
            self.message_timer = 2

    def shoot(self) -> None:
        if self.mag <= 0:
            self.message = "Empty magazine - press R"
            self.message_timer = 2
            return
        self.mag -= 1
        mouse_world = pygame.Vector2(pygame.mouse.get_pos()) + self.camera()
        origin = self.in_vehicle.pos if self.in_vehicle else self.player
        for target in list(self.targets):
            if target.distance_to(mouse_world) < 38 and target.distance_to(origin) < 680:
                self.targets.remove(target)
                self.cash += 25
                self.message = "Target hit +$25"
                self.message_timer = 2
                break

    def draw_world(self, cam: pygame.Vector2) -> None:
        self.screen.fill((123, 185, 224))
        pygame.draw.rect(self.screen, GRASS, (-cam.x, -cam.y, WORLD_W, WORLD_H))
        for x in range(0, WORLD_W, BLOCK):
            pygame.draw.rect(self.screen, SIDEWALK, (x - cam.x - ROAD_W // 2 - 18, -cam.y, ROAD_W + 36, WORLD_H))
            pygame.draw.rect(self.screen, ASPHALT, (x - cam.x - ROAD_W // 2, -cam.y, ROAD_W, WORLD_H))
            pygame.draw.line(self.screen, YELLOW, (x - cam.x, -cam.y), (x - cam.x, WORLD_H - cam.y), 3)
        for y in range(0, WORLD_H, BLOCK):
            pygame.draw.rect(self.screen, SIDEWALK, (-cam.x, y - cam.y - ROAD_W // 2 - 18, WORLD_W, ROAD_W + 36))
            pygame.draw.rect(self.screen, ASPHALT, (-cam.x, y - cam.y - ROAD_W // 2, WORLD_W, ROAD_W))
            pygame.draw.line(self.screen, YELLOW, (-cam.x, y - cam.y), (WORLD_W - cam.x, y - cam.y), 3)
        for bx in range(170, WORLD_W, 260):
            for by in range(150, WORLD_H, 260):
                if (bx % BLOCK) > 120 and (by % BLOCK) > 120:
                    color = random.Random(bx * 31 + by).choice([(180, 160, 135), (150, 165, 175), (205, 190, 165), (115, 125, 135)])
                    pygame.draw.rect(self.screen, color, (bx - cam.x, by - cam.y, 145, 110))
                    pygame.draw.rect(self.screen, (40, 55, 68), (bx - cam.x + 15, by - cam.y + 18, 25, 28))
                    pygame.draw.rect(self.screen, (40, 55, 68), (bx - cam.x + 58, by - cam.y + 18, 25, 28))
                    pygame.draw.rect(self.screen, (40, 55, 68), (bx - cam.x + 101, by - cam.y + 18, 25, 28))
        for palm in range(80, WORLD_W, 240):
            pygame.draw.rect(self.screen, (110, 72, 35), (palm - cam.x, 55 - cam.y, 8, 46))
            pygame.draw.circle(self.screen, (45, 140, 58), (palm - cam.x + 4, 50 - cam.y), 25)
        for target in self.targets:
            pygame.draw.circle(self.screen, RED, target - cam, 28)
            pygame.draw.circle(self.screen, WHITE, target - cam, 18)
            pygame.draw.circle(self.screen, RED, target - cam, 8)
        for mission in self.missions:
            if not mission.complete:
                pygame.draw.circle(self.screen, ORANGE if mission.active else BLUE, mission.pos - cam, 28, 4)
                self.draw_text("F", mission.pos - cam - pygame.Vector2(7, 13), WHITE, self.big)
                if mission.active:
                    pygame.draw.circle(self.screen, GREEN, mission.target - cam, 38, 4)
        for ped in self.peds:
            ped.draw(self.screen, cam)
        near = self.nearest_vehicle()
        for vehicle in self.vehicles:
            vehicle.draw(self.screen, cam, vehicle is near and self.in_vehicle is None)
        if not self.in_vehicle:
            p = self.player - cam
            pygame.draw.circle(self.screen, (34, 76, 108), p, 17)
            pygame.draw.circle(self.screen, (65, 45, 35), p + pygame.Vector2(0, -18), 10)
            pygame.draw.line(self.screen, (235, 235, 225), p, p + vec_from_angle(self.player_angle) * 26, 4)

    def draw_text(self, text: str, pos: Iterable[float], color=WHITE, font: pygame.font.Font | None = None) -> None:
        img = (font or self.font).render(text, True, color)
        self.screen.blit(img, pos)

    def draw_hud(self, cam: pygame.Vector2) -> None:
        minutes = int(self.time_minutes)
        self.draw_text(f"{minutes // 60:02d}:{minutes % 60:02d}", (1110, 18), WHITE, self.big)
        self.draw_text(f"${self.cash}", (1112, 55), GREEN, self.font)
        pygame.draw.circle(self.screen, (28, 34, 42), (1215, 43), 34)
        pygame.draw.circle(self.screen, (92, 58, 40), (1215, 37), 15)
        pygame.draw.rect(self.screen, (25, 74, 106), (1198, 52, 34, 20))
        weapon = "DRIVING" if self.in_vehicle else "OPEN WORLD EXPLORATION"
        if self.targets and not self.in_vehicle and self.player.y > 1250:
            weapon = "SHOOTING"
        self.draw_label(weapon, (12, 10))
        if self.in_vehicle:
            speed = abs(int(self.in_vehicle.speed * 0.18))
            pygame.draw.circle(self.screen, (17, 18, 20), (1148, 615), 72, 4)
            self.draw_text(str(speed), (1125, 578), WHITE, self.big)
            self.draw_text("km/h", (1125, 618), WHITE, self.small)
        else:
            self.draw_text(f"Rifle {self.ammo}  {self.mag}", (1025, 102), WHITE, self.font)
        self.draw_minimap(cam)
        mission = next((m for m in self.missions if m.active), None)
        if mission:
            pygame.draw.rect(self.screen, (0, 0, 0, 185), (12, 458, 285, 105))
            self.draw_text("MISSION", (22, 468), WHITE, self.font)
            self.draw_text(mission.title, (22, 497), WHITE, self.font)
            dist = int((self.player if not self.in_vehicle else self.in_vehicle.pos).distance_to(mission.target))
            self.draw_text(f"{mission.detail} ({dist}m)", (22, 526), WHITE, self.small)
        if self.message_timer > 0:
            self.draw_panel(self.message, (12, 44), 360)
        if self.show_help:
            self.draw_panel("WASD move/drive | E vehicle | F interact | Mouse/Space shoot | R reload | H help", (260, 674), 760)
        if self.paused:
            self.draw_label("PAUSED", (560, 320), self.big)

    def draw_label(self, text: str, pos: tuple[int, int], font: pygame.font.Font | None = None) -> None:
        label = (font or self.font).render(text, True, WHITE)
        box = label.get_rect(topleft=pos).inflate(18, 10)
        pygame.draw.rect(self.screen, BLACK, box)
        self.screen.blit(label, label.get_rect(topleft=(pos[0] + 9, pos[1] + 5)))

    def draw_panel(self, text: str, pos: tuple[int, int], width: int) -> None:
        pygame.draw.rect(self.screen, (0, 0, 0, 170), (*pos, width, 30))
        self.draw_text(text, (pos[0] + 8, pos[1] + 6), WHITE, self.small)

    def draw_minimap(self, cam: pygame.Vector2) -> None:
        rect = pygame.Rect(14, 535, 165, 135)
        pygame.draw.rect(self.screen, (170, 176, 173), rect)
        sx, sy = rect.w / WORLD_W, rect.h / WORLD_H
        for x in range(0, WORLD_W, BLOCK):
            pygame.draw.line(self.screen, (95, 95, 95), (rect.x + x * sx, rect.y), (rect.x + x * sx, rect.bottom), 3)
        for y in range(0, WORLD_H, BLOCK):
            pygame.draw.line(self.screen, (95, 95, 95), (rect.x, rect.y + y * sy), (rect.right, rect.y + y * sy), 3)
        pos = self.in_vehicle.pos if self.in_vehicle else self.player
        pygame.draw.circle(self.screen, WHITE, (rect.x + pos.x * sx, rect.y + pos.y * sy), 5)
        pygame.draw.rect(self.screen, BLACK, rect, 3)
        pygame.draw.rect(self.screen, GREEN, (14, 674, 72, 7))
        pygame.draw.rect(self.screen, BLUE, (86, 674, 46, 7))
        pygame.draw.rect(self.screen, YELLOW, (132, 674, 47, 7))

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000
            for event in pygame.event.get():
                running = self.handle_event(event)
            self.update(dt)
            cam = self.camera()
            self.draw_world(cam)
            self.draw_hud(cam)
            pygame.display.flip()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
