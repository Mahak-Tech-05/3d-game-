"""Metro Renegade - a complete original Python/Pygame urban action game.

This project avoids copyrighted assets and trademarked content. It presents an
original top-down/third-person-inspired sandbox with missions, combat, driving,
progression, win/lose states, and no prone mechanic.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pygame

WIDTH, HEIGHT = 1280, 720
FPS = 60
WORLD_W, WORLD_H = 3600, 2600
ROAD_W = 172
BLOCK = 520
SAVE_FILE = Path("savegame.json")
WHITE = (245, 245, 238)
YELLOW = (232, 202, 71)
GREEN = (42, 210, 80)
RED = (225, 60, 52)
BLUE = (69, 155, 239)
BLACK = (8, 10, 14)
ORANGE = (255, 161, 65)
PURPLE = (172, 88, 255)
ASPHALT = (60, 61, 64)
SIDEWALK = (207, 201, 190)
GRASS = (68, 122, 66)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def vec_from_angle(angle: float) -> pygame.Vector2:
    return pygame.Vector2(math.cos(angle), math.sin(angle))


def safe_normalize(vector: pygame.Vector2) -> pygame.Vector2:
    if vector.length_squared() == 0:
        return pygame.Vector2()
    return vector.normalize()


@dataclass
class Vehicle:
    pos: pygame.Vector2
    color: tuple[int, int, int]
    name: str
    speed: float = 0.0
    angle: float = 0.0
    kind: str = "car"
    durability: float = 100.0

    @property
    def size(self) -> tuple[int, int]:
        return (68, 36) if self.kind == "car" else (50, 22)

    def update_player(self, dt: float, keys: pygame.key.ScancodeWrapper) -> None:
        accel = 700 if keys[pygame.K_w] or keys[pygame.K_UP] else 0
        reverse = 390 if keys[pygame.K_s] or keys[pygame.K_DOWN] else 0
        self.speed += (accel - reverse) * dt
        friction = 2.1 if keys[pygame.K_LSHIFT] else 1.08
        self.speed -= self.speed * friction * dt
        self.speed = clamp(self.speed, -235, 660)
        turn = int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT])
        turn_strength = 2.7 * (0.22 + min(abs(self.speed) / 350, 1.0))
        self.angle += turn * turn_strength * dt * (1 if self.speed >= 0 else -1)
        self.pos += vec_from_angle(self.angle) * self.speed * dt
        self.pos.x = clamp(self.pos.x, 45, WORLD_W - 45)
        self.pos.y = clamp(self.pos.y, 45, WORLD_H - 45)

    def draw(self, surface: pygame.Surface, camera: pygame.Vector2, selected: bool = False) -> None:
        w, h = self.size
        car = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rounded_rect(car, self.color, (0, 0, w, h), 10)
        pygame.draw.rounded_rect(car, (24, 29, 36), (w * 0.28, 5, w * 0.38, h - 10), 5)
        pygame.draw.rect(car, (235, 236, 210), (w - 9, 6, 6, 9))
        pygame.draw.rect(car, (190, 25, 28), (2, 6, 6, 9))
        if self.kind == "bike":
            pygame.draw.circle(car, BLACK, (8, h // 2), 7)
            pygame.draw.circle(car, BLACK, (w - 8, h // 2), 7)
        rotated = pygame.transform.rotate(car, -math.degrees(self.angle))
        surface.blit(rotated, rotated.get_rect(center=self.pos - camera))
        if selected:
            pygame.draw.circle(surface, YELLOW, self.pos - camera, 48, 2)


@dataclass
class Pedestrian:
    pos: pygame.Vector2
    color: tuple[int, int, int]
    direction: pygame.Vector2 = field(default_factory=lambda: pygame.Vector2(1, 0))
    timer: float = 0.0

    def update(self, dt: float) -> None:
        self.timer -= dt
        if self.timer <= 0:
            self.direction = safe_normalize(pygame.Vector2(random.uniform(-1, 1), random.uniform(-1, 1)))
            self.timer = random.uniform(0.8, 3.2)
        self.pos += self.direction * 38 * dt
        self.pos.x = clamp(self.pos.x, 60, WORLD_W - 60)
        self.pos.y = clamp(self.pos.y, 60, WORLD_H - 60)

    def draw(self, surface: pygame.Surface, camera: pygame.Vector2) -> None:
        p = self.pos - camera
        pygame.draw.circle(surface, self.color, p, 7)
        pygame.draw.line(surface, (35, 35, 38), (p.x, p.y + 7), (p.x, p.y + 18), 3)


@dataclass
class Enemy:
    pos: pygame.Vector2
    faction: str
    health: float = 55.0
    cooldown: float = 0.0

    def update(self, dt: float, player_pos: pygame.Vector2, game: "Game") -> None:
        to_player = player_pos - self.pos
        distance = to_player.length()
        if distance > 26:
            self.pos += safe_normalize(to_player) * (92 if self.faction == "police" else 70) * dt
        self.cooldown = max(0, self.cooldown - dt)
        if distance < 260 and self.cooldown <= 0:
            game.damage_player(5 if self.faction == "police" else 8)
            self.cooldown = 0.9

    def draw(self, surface: pygame.Surface, camera: pygame.Vector2) -> None:
        p = self.pos - camera
        color = BLUE if self.faction == "police" else RED
        pygame.draw.circle(surface, color, p, 13)
        pygame.draw.rect(surface, BLACK, (p.x - 18, p.y - 24, 36, 5))
        pygame.draw.rect(surface, GREEN, (p.x - 18, p.y - 24, 36 * clamp(self.health / 55, 0, 1), 5))


@dataclass
class Mission:
    title: str
    briefing: str
    start: pygame.Vector2
    target: pygame.Vector2
    reward: int
    goal: str
    required: int = 1
    progress: int = 0
    active: bool = False
    complete: bool = False

    def objective_text(self, player_pos: pygame.Vector2) -> str:
        distance = int(player_pos.distance_to(self.target))
        return f"{self.briefing} | {self.progress}/{self.required} | {distance}m"


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Metro Renegade - Complete Python Open World")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 20, bold=True)
        self.small = pygame.font.SysFont("arial", 15)
        self.big = pygame.font.SysFont("arial", 34, bold=True)
        self.huge = pygame.font.SysFont("arial", 72, bold=True)
        self.state = "menu"
        self.reset_world(load_save=True)

    def reset_world(self, load_save: bool = False) -> None:
        self.player = pygame.Vector2(760, 720)
        self.player_angle = 0.0
        self.health = 100.0
        self.armor = 35.0
        self.wanted = 0
        self.heat_timer = 0.0
        self.in_vehicle: Vehicle | None = None
        self.cash = 1500
        self.score = 0
        self.ammo = 220
        self.mag = 30
        self.time_minutes = 12 * 60 + 45
        self.show_help = True
        self.paused = False
        self.radio = 0
        self.message = "Start a mission at a blue marker. No prone mechanic."
        self.message_timer = 6.0
        self.enemies: list[Enemy] = []
        self.particles: list[tuple[pygame.Vector2, pygame.Vector2, float, tuple[int, int, int]]] = []
        self.vehicles = [
            Vehicle(pygame.Vector2(850, 720), (24, 31, 40), "Shadow Sedan"),
            Vehicle(pygame.Vector2(1220, 1080), (215, 46, 34), "Crimson Cabrio"),
            Vehicle(pygame.Vector2(1740, 710), (245, 245, 238), "Pearl Sport"),
            Vehicle(pygame.Vector2(1820, 780), (35, 116, 230), "Azure Coupe"),
            Vehicle(pygame.Vector2(1660, 820), (95, 210, 53), "Lime Bike", kind="bike"),
            Vehicle(pygame.Vector2(2880, 1860), (252, 184, 55), "Gold Interceptor"),
        ]
        self.peds = [Pedestrian(pygame.Vector2(random.randrange(80, WORLD_W - 80), random.randrange(80, WORLD_H - 80)), random.choice([(230, 190, 145), (110, 80, 55), (245, 220, 170)])) for _ in range(95)]
        self.missions = [
            Mission("REPOSSESSION", "Recover the pearl sport car", pygame.Vector2(640, 940), pygame.Vector2(1740, 710), 850, "reach"),
            Mission("TARGET PRACTICE", "Clear the alley targets", pygame.Vector2(520, 1470), pygame.Vector2(780, 1560), 700, "targets", 8),
            Mission("HEAT RUN", "Survive the pursuit and reach the safehouse", pygame.Vector2(2080, 1000), pygame.Vector2(3040, 2050), 1200, "escape"),
            Mission("FINAL DELIVERY", "Drive the gold car to the studio finale", pygame.Vector2(2870, 1840), pygame.Vector2(3400, 420), 1800, "finale"),
        ]
        self.targets = [pygame.Vector2(520 + i * 95, 1540 + (i % 2) * 55) for i in range(8)]
        if load_save and SAVE_FILE.exists():
            data = json.loads(SAVE_FILE.read_text())
            self.cash = int(data.get("cash", self.cash))
            self.score = int(data.get("score", self.score))
            completed = set(data.get("completed", []))
            for mission in self.missions:
                mission.complete = mission.title in completed

    def save(self) -> None:
        data = {"cash": self.cash, "score": self.score, "completed": [m.title for m in self.missions if m.complete]}
        SAVE_FILE.write_text(json.dumps(data, indent=2))
        self.message = "Game saved"
        self.message_timer = 2

    @property
    def player_pos(self) -> pygame.Vector2:
        return self.in_vehicle.pos if self.in_vehicle else self.player

    def camera(self) -> pygame.Vector2:
        focus = self.player_pos
        return pygame.Vector2(clamp(focus.x - WIDTH / 2, 0, WORLD_W - WIDTH), clamp(focus.y - HEIGHT / 2, 0, WORLD_H - HEIGHT))

    def active_mission(self) -> Mission | None:
        return next((m for m in self.missions if m.active), None)

    def update(self, dt: float) -> None:
        if self.state != "play" or self.paused:
            return
        keys = pygame.key.get_pressed()
        self.time_minutes = (self.time_minutes + dt * 1.8) % (24 * 60)
        self.message_timer = max(0, self.message_timer - dt)
        self.heat_timer = max(0, self.heat_timer - dt)
        if self.heat_timer == 0 and self.wanted > 0:
            self.wanted -= 1
            self.heat_timer = 4
        if self.in_vehicle:
            old_speed = abs(self.in_vehicle.speed)
            self.in_vehicle.update_player(dt, keys)
            self.player = self.in_vehicle.pos - vec_from_angle(self.in_vehicle.angle) * 30
            if old_speed > 520 and random.random() < 0.008:
                self.raise_wanted(1)
        else:
            move = pygame.Vector2(int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT]), int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP]))
            if move.length_squared():
                move.normalize_ip()
                self.player_angle = math.atan2(move.y, move.x)
            self.player += move * (235 if keys[pygame.K_LSHIFT] else 148) * dt
            self.player.x = clamp(self.player.x, 35, WORLD_W - 35)
            self.player.y = clamp(self.player.y, 35, WORLD_H - 35)
        for ped in self.peds:
            ped.update(dt)
        for enemy in list(self.enemies):
            enemy.update(dt, self.player_pos, self)
            if enemy.health <= 0:
                self.enemies.remove(enemy)
                self.cash += 60
                self.score += 100
        if self.wanted > 0 and len([e for e in self.enemies if e.faction == "police"]) < self.wanted + 1:
            self.spawn_enemy("police")
        self.update_particles(dt)
        self.update_missions()
        if self.health <= 0:
            self.state = "gameover"
        if all(m.complete for m in self.missions):
            self.save()
            self.state = "victory"

    def update_missions(self) -> None:
        mission = self.active_mission()
        if not mission:
            return
        pos = self.player_pos
        if mission.goal == "reach" and pos.distance_to(mission.target) < 80:
            mission.progress = 1
            self.finish_mission(mission)
        elif mission.goal == "targets":
            mission.progress = 8 - len(self.targets)
            if mission.progress >= mission.required:
                self.finish_mission(mission)
        elif mission.goal == "escape":
            if not any(e.faction == "police" for e in self.enemies):
                self.raise_wanted(3)
            if pos.distance_to(mission.target) < 95 and self.wanted <= 1:
                mission.progress = 1
                self.finish_mission(mission)
        elif mission.goal == "finale":
            driving_gold = self.in_vehicle and self.in_vehicle.name == "Gold Interceptor"
            if driving_gold and pos.distance_to(mission.target) < 95:
                mission.progress = 1
                self.finish_mission(mission)

    def finish_mission(self, mission: Mission) -> None:
        mission.complete = True
        mission.active = False
        self.cash += mission.reward
        self.score += mission.reward * 2
        self.wanted = max(0, self.wanted - 1)
        self.message = f"MISSION PASSED: {mission.title} +${mission.reward}"
        self.message_timer = 5
        self.save()

    def spawn_enemy(self, faction: str) -> None:
        angle = random.uniform(0, math.tau)
        offset = vec_from_angle(angle) * random.randrange(420, 620)
        pos = self.player_pos + offset
        pos.x = clamp(pos.x, 80, WORLD_W - 80)
        pos.y = clamp(pos.y, 80, WORLD_H - 80)
        self.enemies.append(Enemy(pos, faction))

    def damage_player(self, amount: float) -> None:
        if self.armor > 0:
            absorbed = min(self.armor, amount * 0.65)
            self.armor -= absorbed
            amount -= absorbed
        self.health -= amount
        self.message = "Taking fire! Keep moving."
        self.message_timer = 1.2

    def raise_wanted(self, amount: int) -> None:
        self.wanted = min(5, self.wanted + amount)
        self.heat_timer = 8

    def nearest_vehicle(self) -> Vehicle | None:
        near = min(self.vehicles, key=lambda v: v.pos.distance_to(self.player_pos))
        return near if near.pos.distance_to(self.player_pos) < 92 else None

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if self.state == "menu":
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.state = "play"
                elif event.key == pygame.K_n:
                    self.reset_world(load_save=False)
                    self.state = "play"
                elif event.key == pygame.K_q:
                    return False
                return True
            if self.state in {"gameover", "victory"}:
                if event.key == pygame.K_RETURN:
                    self.reset_world(load_save=False)
                    self.state = "play"
                elif event.key == pygame.K_q:
                    return False
                return True
            if event.key == pygame.K_ESCAPE:
                self.paused = not self.paused
            elif event.key == pygame.K_h:
                self.show_help = not self.show_help
            elif event.key == pygame.K_F5:
                self.save()
            elif event.key == pygame.K_TAB:
                self.radio = (self.radio + 1) % 4
                self.message = ["Radio: Downtown Pulse", "Radio: Coastline Funk", "Radio: Night Drive", "Radio off"][self.radio]
                self.message_timer = 3
            elif event.key == pygame.K_e:
                self.toggle_vehicle()
            elif event.key == pygame.K_f:
                self.interact()
            elif event.key == pygame.K_r:
                used = min(30, self.ammo)
                self.mag = used
                self.message = "Reloaded" if used else "No reserve ammo"
                self.message_timer = 2
            elif event.key == pygame.K_1:
                self.cash = max(0, self.cash - 150)
                self.armor = min(100, self.armor + 35)
                self.message = "Bought armor +35"
                self.message_timer = 2
        if self.state == "play" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.shoot()
        if self.state == "play" and event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
            self.shoot()
        return True

    def toggle_vehicle(self) -> None:
        if self.in_vehicle:
            self.player = self.in_vehicle.pos + pygame.Vector2(54, 0).rotate_rad(self.in_vehicle.angle)
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

    def interact(self) -> None:
        for mission in self.missions:
            if not mission.complete and not any(m.active for m in self.missions) and self.player_pos.distance_to(mission.start) < 95:
                mission.active = True
                if mission.goal == "escape":
                    self.raise_wanted(3)
                if mission.goal == "finale":
                    self.message = "Find and drive the Gold Interceptor to the finale marker."
                else:
                    self.message = f"Mission started: {mission.title}"
                self.message_timer = 4
                return
        if self.player_pos.distance_to(pygame.Vector2(1740, 760)) < 180:
            self.cash = max(0, self.cash - 75)
            self.health = min(100, self.health + 30)
            self.armor = min(100, self.armor + 20)
            self.message = "Garage repaired you for $75"
        else:
            self.message = "Nothing to interact with here"
        self.message_timer = 2.5

    def shoot(self) -> None:
        if self.paused or self.mag <= 0:
            self.message = "Empty magazine - press R" if self.mag <= 0 else "Paused"
            self.message_timer = 2
            return
        self.mag -= 1
        self.ammo = max(0, self.ammo - 1)
        origin = self.player_pos
        mouse_world = pygame.Vector2(pygame.mouse.get_pos()) + self.camera()
        direction = safe_normalize(mouse_world - origin)
        self.player_angle = math.atan2(direction.y, direction.x) if direction.length_squared() else self.player_angle
        for _ in range(8):
            self.particles.append((origin.copy(), direction.rotate(random.uniform(-4, 4)) * random.uniform(380, 620), 0.24, YELLOW))
        for target in list(self.targets):
            if target.distance_to(mouse_world) < 42 and target.distance_to(origin) < 720:
                self.targets.remove(target)
                self.cash += 25
                self.score += 50
                self.message = "Target hit +$25"
                self.message_timer = 2
                return
        for enemy in self.enemies:
            if enemy.pos.distance_to(mouse_world) < 45 and enemy.pos.distance_to(origin) < 760:
                enemy.health -= 32
                self.raise_wanted(1 if enemy.faction != "police" else 2)
                return
        if random.random() < 0.35:
            self.raise_wanted(1)

    def update_particles(self, dt: float) -> None:
        updated = []
        for pos, velocity, life, color in self.particles:
            pos += velocity * dt
            life -= dt
            if life > 0:
                updated.append((pos, velocity * 0.86, life, color))
        self.particles = updated

    def draw(self) -> None:
        if self.state == "menu":
            self.draw_menu()
            return
        if self.state in {"gameover", "victory"}:
            self.draw_end_screen()
            return
        cam = self.camera()
        self.draw_world(cam)
        self.draw_hud(cam)
        pygame.display.flip()

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
                    rng = random.Random(bx * 31 + by)
                    color = rng.choice([(180, 160, 135), (150, 165, 175), (205, 190, 165), (115, 125, 135)])
                    pygame.draw.rect(self.screen, color, (bx - cam.x, by - cam.y, 145, 110))
                    for wx in (15, 58, 101):
                        pygame.draw.rect(self.screen, (40, 55, 68), (bx - cam.x + wx, by - cam.y + 18, 25, 28))
        for palm in range(80, WORLD_W, 240):
            pygame.draw.rect(self.screen, (110, 72, 35), (palm - cam.x, 55 - cam.y, 8, 46))
            pygame.draw.circle(self.screen, (45, 140, 58), (palm - cam.x + 4, 50 - cam.y), 25)
        for target in self.targets:
            pygame.draw.circle(self.screen, RED, target - cam, 28)
            pygame.draw.circle(self.screen, WHITE, target - cam, 18)
            pygame.draw.circle(self.screen, RED, target - cam, 8)
        for mission in self.missions:
            if not mission.complete:
                color = ORANGE if mission.active else BLUE
                pygame.draw.circle(self.screen, color, mission.start - cam, 30, 4)
                self.draw_text("F", mission.start - cam - pygame.Vector2(7, 13), WHITE, self.big)
                if mission.active:
                    pygame.draw.circle(self.screen, GREEN if mission.goal != "finale" else PURPLE, mission.target - cam, 40, 4)
        for ped in self.peds:
            ped.draw(self.screen, cam)
        near = self.nearest_vehicle()
        for vehicle in self.vehicles:
            vehicle.draw(self.screen, cam, vehicle is near and self.in_vehicle is None)
        for enemy in self.enemies:
            enemy.draw(self.screen, cam)
        for pos, _velocity, _life, color in self.particles:
            pygame.draw.circle(self.screen, color, pos - cam, 3)
        if not self.in_vehicle:
            p = self.player - cam
            pygame.draw.circle(self.screen, (34, 76, 108), p, 17)
            pygame.draw.circle(self.screen, (65, 45, 35), p + pygame.Vector2(0, -18), 10)
            pygame.draw.line(self.screen, (235, 235, 225), p, p + vec_from_angle(self.player_angle) * 27, 4)

    def draw_hud(self, cam: pygame.Vector2) -> None:
        minutes = int(self.time_minutes)
        self.draw_text(f"{minutes // 60:02d}:{minutes % 60:02d}", (1110, 18), WHITE, self.big)
        self.draw_text(f"${self.cash}", (1112, 55), GREEN, self.font)
        self.draw_text(f"Score {self.score}", (1112, 82), WHITE, self.small)
        pygame.draw.circle(self.screen, (28, 34, 42), (1215, 43), 34)
        pygame.draw.circle(self.screen, (92, 58, 40), (1215, 37), 15)
        pygame.draw.rect(self.screen, (25, 74, 106), (1198, 52, 34, 20))
        mode = "DRIVING" if self.in_vehicle else "OPEN WORLD EXPLORATION"
        if self.active_mission() and self.active_mission().goal == "targets":
            mode = "SHOOTING"
        self.draw_label(mode, (12, 10))
        self.draw_bars()
        self.draw_wanted()
        if self.in_vehicle:
            speed = abs(int(self.in_vehicle.speed * 0.18))
            pygame.draw.circle(self.screen, (17, 18, 20), (1148, 615), 72, 4)
            self.draw_text(str(speed), (1125, 578), WHITE, self.big)
            self.draw_text("km/h", (1125, 618), WHITE, self.small)
        else:
            self.draw_text(f"Rifle {self.ammo}  {self.mag}", (1025, 112), WHITE, self.font)
        self.draw_minimap()
        mission = self.active_mission()
        if mission:
            pygame.draw.rect(self.screen, (0, 0, 0), (12, 440, 390, 123))
            self.draw_text("MISSION", (22, 450), WHITE, self.font)
            self.draw_text(mission.title, (22, 480), WHITE, self.font)
            self.draw_text(mission.objective_text(self.player_pos), (22, 512), WHITE, self.small)
        if self.message_timer > 0:
            self.draw_panel(self.message, (12, 44), 520)
        if self.show_help:
            self.draw_panel("WASD move/drive | E vehicle | F mission/garage | Shoot mouse/Space | R reload | 1 armor | F5 save", (220, 674), 850)
        if self.paused:
            self.draw_label("PAUSED", (560, 320), self.big)

    def draw_bars(self) -> None:
        pygame.draw.rect(self.screen, BLACK, (22, 80, 182, 14))
        pygame.draw.rect(self.screen, RED, (24, 82, 178 * clamp(self.health / 100, 0, 1), 10))
        pygame.draw.rect(self.screen, BLACK, (22, 100, 182, 14))
        pygame.draw.rect(self.screen, BLUE, (24, 102, 178 * clamp(self.armor / 100, 0, 1), 10))
        self.draw_text("HP", (210, 76), WHITE, self.small)
        self.draw_text("AR", (210, 96), WHITE, self.small)

    def draw_wanted(self) -> None:
        for i in range(5):
            self.draw_text("★", (1025 + i * 22, 55), YELLOW if i < self.wanted else (70, 70, 75), self.font)

    def draw_minimap(self) -> None:
        rect = pygame.Rect(14, 535, 165, 135)
        pygame.draw.rect(self.screen, (170, 176, 173), rect)
        sx, sy = rect.w / WORLD_W, rect.h / WORLD_H
        for x in range(0, WORLD_W, BLOCK):
            pygame.draw.line(self.screen, (95, 95, 95), (rect.x + x * sx, rect.y), (rect.x + x * sx, rect.bottom), 3)
        for y in range(0, WORLD_H, BLOCK):
            pygame.draw.line(self.screen, (95, 95, 95), (rect.x, rect.y + y * sy), (rect.right, rect.y + y * sy), 3)
        pygame.draw.circle(self.screen, WHITE, (rect.x + self.player_pos.x * sx, rect.y + self.player_pos.y * sy), 5)
        for mission in self.missions:
            if not mission.complete:
                pygame.draw.circle(self.screen, BLUE, (rect.x + mission.start.x * sx, rect.y + mission.start.y * sy), 4)
        pygame.draw.rect(self.screen, BLACK, rect, 3)
        pygame.draw.rect(self.screen, GREEN, (14, 674, 72, 7))
        pygame.draw.rect(self.screen, BLUE, (86, 674, 46, 7))
        pygame.draw.rect(self.screen, YELLOW, (132, 674, 47, 7))

    def draw_menu(self) -> None:
        self.screen.fill((12, 17, 24))
        pygame.draw.rect(self.screen, (21, 34, 48), (0, 430, WIDTH, 290))
        self.draw_text("METRO RENEGADE", (250, 125), WHITE, self.huge)
        self.draw_text("A complete Python open-world action game", (360, 215), YELLOW, self.big)
        self.draw_text("ENTER/SPACE: continue  |  N: new game  |  Q: quit", (365, 310), WHITE, self.font)
        self.draw_text("Finish all four missions, survive police heat, earn cash, and reach the finale.", (285, 360), WHITE, self.font)
        self.draw_text("No prone mechanic. Original procedural art. Fully Python + Pygame.", (335, 395), GREEN, self.font)
        pygame.display.flip()

    def draw_end_screen(self) -> None:
        self.screen.fill((8, 10, 14))
        title = "CITY LEGEND" if self.state == "victory" else "WASTED"
        color = GREEN if self.state == "victory" else RED
        self.draw_text(title, (430, 170), color, self.huge)
        self.draw_text(f"Final cash: ${self.cash}     Score: {self.score}", (410, 295), WHITE, self.big)
        self.draw_text("ENTER: new game     Q: quit", (455, 380), WHITE, self.font)
        pygame.display.flip()

    def draw_text(self, text: str, pos: Iterable[float], color=WHITE, font: pygame.font.Font | None = None) -> None:
        img = (font or self.font).render(text, True, color)
        self.screen.blit(img, pos)

    def draw_label(self, text: str, pos: tuple[int, int], font: pygame.font.Font | None = None) -> None:
        label = (font or self.font).render(text, True, WHITE)
        box = label.get_rect(topleft=pos).inflate(18, 10)
        pygame.draw.rect(self.screen, BLACK, box)
        self.screen.blit(label, label.get_rect(topleft=(pos[0] + 9, pos[1] + 5)))

    def draw_panel(self, text: str, pos: tuple[int, int], width: int) -> None:
        pygame.draw.rect(self.screen, (0, 0, 0), (*pos, width, 30))
        self.draw_text(text, (pos[0] + 8, pos[1] + 6), WHITE, self.small)

    def run(self) -> None:
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000
            for event in pygame.event.get():
                running = self.handle_event(event)
            self.update(dt)
            self.draw()
        pygame.quit()


if __name__ == "__main__":
    Game().run()
