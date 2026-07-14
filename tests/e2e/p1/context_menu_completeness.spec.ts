import { expect, test } from "@playwright/test";

const worldFixture = {
  container: {
    id: "ctx_folder",
    name: "Context Folder",
    type: "notebook" as const,
    sortOrder: 200,
  },
  item: {
    id: "ctx_item",
    containerId: "ctx_folder",
    type: "concept",
    name: "Context Item",
    description: "",
    attributes: [],
    linkedCharacterIds: [],
    linkedEventIds: [],
    linkedSceneIds: [],
    mapMarkers: [],
    tagIds: [],
  },
};

async function openWorldFixture(page: import("@playwright/test").Page) {
  await page.goto("/world");
  await page.evaluate(({ container, item }) => {
    (window as any).__narrativeStore.setState((state: any) => ({
      worldContainers: [...state.worldContainers, container],
      worldItems: [...state.worldItems, item],
    }));
  }, worldFixture);
  await page.getByTestId("world-container-ctx_folder").click();
}

test("character context menu exposes complete commands and explains unavailable actions", async ({
  page,
}) => {
  await page.goto("/characters/list");
  await page.getByTestId("character-card-char_aria").click({ button: "right" });

  for (const id of [
    "character-new",
    "character-copy",
    "character-cut",
    "character-paste",
    "character-rename",
    "character-move",
    "character-merge",
    "character-archive",
    "character-delete",
  ]) {
    await expect(page.getByTestId(`context-menu-item-${id}`)).toBeVisible();
  }
  await expect(
    page.getByTestId("context-menu-item-character-merge"),
  ).toBeDisabled();
  await expect(
    page.getByTestId("context-menu-item-character-merge"),
  ).toHaveAttribute("title", /not available/i);
});

test("hard delete character clears every cross-module reference and one undo restores them", async ({
  page,
}) => {
  await page.goto("/characters/list");
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.setState((state: any) => ({
      characters: [
        ...state.characters,
        {
          id: "hard_delete_character",
          name: "Hard Delete Character",
          relationshipIds: ["hard_delete_relationship"],
        },
        {
          id: "hard_delete_survivor",
          name: "Hard Delete Survivor",
          relationshipIds: ["hard_delete_relationship"],
        },
      ],
      relationships: [
        ...state.relationships,
        {
          id: "hard_delete_relationship",
          sourceId: "hard_delete_character",
          targetId: "hard_delete_survivor",
        },
      ],
      timelineEvents: [
        ...state.timelineEvents,
        {
          id: "hard_delete_event",
          participantCharacterIds: ["hard_delete_character"],
        },
      ],
      scenes: [
        ...state.scenes,
        {
          id: "hard_delete_scene",
          povCharacterId: "hard_delete_character",
          linkedCharacterIds: ["hard_delete_character"],
        },
      ],
      worldItems: [
        ...state.worldItems,
        {
          id: "hard_delete_world",
          linkedCharacterIds: ["hard_delete_character"],
        },
      ],
      characterTags: [
        ...state.characterTags,
        { id: "hard_delete_tag", characterIds: ["hard_delete_character"] },
      ],
      graphBoards: [
        ...state.graphBoards,
        {
          id: "hard_delete_graph",
          name: "Hard Delete Graph",
          description: "",
          sortOrder: 0,
          selectedNodeIds: [],
          edges: [],
          view: { zoom: 1, panX: 0, panY: 0 },
          nodes: [
            {
              id: "hard_delete_node",
              kind: "character_ref",
              label: "Hard Delete Character",
              description: "",
              x: 0,
              y: 0,
              width: 100,
              height: 80,
              linkedEntityId: "hard_delete_character",
              linkedEntityType: "character",
            },
          ],
        },
      ],
      scripts: [
        ...state.scripts,
        {
          id: "hard_delete_script",
          linkedCharacterIds: ["hard_delete_character"],
        },
      ],
      storyboards: [
        ...state.storyboards,
        {
          id: "hard_delete_storyboard",
          shots: [
            {
              id: "hard_delete_shot",
              linkedCharacterIds: ["hard_delete_character"],
            },
          ],
        },
      ],
      undoStack: [],
      redoStack: [],
    }));
    store.getState().hardDeleteCharacter("hard_delete_character");
  });

  await expect
    .poll(() =>
      page.evaluate(() => {
        const state = (window as any).__narrativeStore.getState();
        return {
          exists: state.characters.some(
            (character: any) => character.id === "hard_delete_character",
          ),
          survivorRelationships: state.characters.find(
            (character: any) => character.id === "hard_delete_survivor",
          ).relationshipIds,
          relationships: state.relationships.filter(
            (relationship: any) =>
              relationship.id === "hard_delete_relationship",
          ).length,
          event: state.timelineEvents.find(
            (event: any) => event.id === "hard_delete_event",
          ).participantCharacterIds,
          scene: (() => {
            const scene = state.scenes.find(
              (entry: any) => entry.id === "hard_delete_scene",
            );
            return {
              pov: scene.povCharacterId,
              linked: scene.linkedCharacterIds,
            };
          })(),
          world: state.worldItems.find(
            (item: any) => item.id === "hard_delete_world",
          ).linkedCharacterIds,
          tag: state.characterTags.find(
            (tag: any) => tag.id === "hard_delete_tag",
          ).characterIds,
          graph: state.graphBoards.find(
            (board: any) => board.id === "hard_delete_graph",
          ).nodes[0].linkedEntityId,
          script: state.scripts.find(
            (script: any) => script.id === "hard_delete_script",
          ).linkedCharacterIds,
          storyboard: state.storyboards.find(
            (storyboard: any) => storyboard.id === "hard_delete_storyboard",
          ).shots[0].linkedCharacterIds,
          undoDepth: state.undoStack.length,
        };
      }),
    )
    .toEqual({
      exists: false,
      survivorRelationships: [],
      relationships: 0,
      event: [],
      scene: { pov: null, linked: [] },
      world: [],
      tag: [],
      graph: null,
      script: [],
      storyboard: [],
      undoDepth: 1,
    });

  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });
  await expect
    .poll(() =>
      page.evaluate(() => {
        const state = (window as any).__narrativeStore.getState();
        return {
          exists: state.characters.some(
            (character: any) => character.id === "hard_delete_character",
          ),
          survivorRelationships: state.characters.find(
            (character: any) => character.id === "hard_delete_survivor",
          ).relationshipIds,
          relationships: state.relationships.filter(
            (relationship: any) =>
              relationship.id === "hard_delete_relationship",
          ).length,
          event: state.timelineEvents.find(
            (event: any) => event.id === "hard_delete_event",
          ).participantCharacterIds,
          scene: (() => {
            const scene = state.scenes.find(
              (entry: any) => entry.id === "hard_delete_scene",
            );
            return {
              pov: scene.povCharacterId,
              linked: scene.linkedCharacterIds,
            };
          })(),
          world: state.worldItems.find(
            (item: any) => item.id === "hard_delete_world",
          ).linkedCharacterIds,
          tag: state.characterTags.find(
            (tag: any) => tag.id === "hard_delete_tag",
          ).characterIds,
          graph: state.graphBoards.find(
            (board: any) => board.id === "hard_delete_graph",
          ).nodes[0].linkedEntityId,
          script: state.scripts.find(
            (script: any) => script.id === "hard_delete_script",
          ).linkedCharacterIds,
          storyboard: state.storyboards.find(
            (storyboard: any) => storyboard.id === "hard_delete_storyboard",
          ).shots[0].linkedCharacterIds,
          undoDepth: state.undoStack.length,
        };
      }),
    )
    .toEqual({
      exists: true,
      survivorRelationships: ["hard_delete_relationship"],
      relationships: 1,
      event: ["hard_delete_character"],
      scene: {
        pov: "hard_delete_character",
        linked: ["hard_delete_character"],
      },
      world: ["hard_delete_character"],
      tag: ["hard_delete_character"],
      graph: "hard_delete_character",
      script: ["hard_delete_character"],
      storyboard: ["hard_delete_character"],
      undoDepth: 0,
    });
});

test("character impact modal blocks hard delete for world, tag, and graph references", async ({
  page,
}) => {
  await page.goto("/characters/list");
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.setState((state: any) => ({
      worldItems: [
        ...state.worldItems,
        { id: "impact_world", linkedCharacterIds: ["char_aria"] },
      ],
      characterTags: [
        ...state.characterTags,
        {
          id: "impact_tag",
          name: "Impact",
          color: "#fff",
          description: "",
          characterIds: ["char_aria"],
        },
      ],
      graphBoards: [
        ...state.graphBoards,
        {
          id: "impact_graph",
          name: "Impact Graph",
          description: "",
          sortOrder: 0,
          selectedNodeIds: [],
          edges: [],
          view: { zoom: 1, panX: 0, panY: 0 },
          nodes: [
            {
              id: "impact_node",
              kind: "character_ref",
              label: "Aria",
              description: "",
              x: 0,
              y: 0,
              width: 100,
              height: 80,
              linkedEntityId: "char_aria",
              linkedEntityType: "character",
            },
          ],
        },
      ],
    }));
  });
  await page.getByTestId("character-card-char_aria").click({ button: "right" });
  await page.getByTestId("context-menu-item-character-archive").click();
  await page.getByTestId("context-menu-item-character-archive").click();

  await expect(page.getByTestId("archive-impact-modal")).toBeVisible();
  await expect(page.getByTestId("archive-impact-list")).toBeVisible();
  await expect(page.getByTestId("archive-impact-world-items")).toBeVisible();
  await expect(page.getByTestId("archive-impact-tags")).toBeVisible();
  await expect(page.getByTestId("archive-impact-graphs")).toBeVisible();
  await expect(page.getByTestId("hard-delete-confirm-btn")).toHaveCount(0);
});

test("world item context menu supports copy and paste and reports disabled move", async ({
  page,
}) => {
  await openWorldFixture(page);
  const item = page.getByTestId("world-item-ctx_item");
  await item.click({ button: "right" });

  for (const id of [
    "world-item-new",
    "world-item-copy",
    "world-item-cut",
    "world-item-paste",
    "world-item-rename",
    "world-item-move",
    "world-item-merge",
    "world-item-delete",
  ]) {
    await expect(page.getByTestId(`context-menu-item-${id}`)).toBeVisible();
  }
  await expect(
    page.getByTestId("context-menu-item-world-item-paste"),
  ).toBeDisabled();
  await expect(
    page.getByTestId("context-menu-item-world-item-paste"),
  ).toHaveAttribute("title", "Copy a world item first");
  await page.getByTestId("context-menu-item-world-item-copy").click();

  await item.click({ button: "right" });
  await page.getByTestId("context-menu-item-world-item-paste").click();
  await expect(page.getByTestId("world-item-list")).toContainText(
    "Context Item (copy)",
  );
  await item.click({ button: "right" });
  await expect(
    page.getByTestId("context-menu-item-world-item-move"),
  ).toBeDisabled();
  await expect(
    page.getByTestId("context-menu-item-world-item-move"),
  ).toHaveAttribute("title", /drag the item/i);
});

test("world folder menu is complete and world UI uses folder language", async ({
  page,
}) => {
  await openWorldFixture(page);
  const folder = page.getByTestId("world-container-ctx_folder");
  await folder.click({ button: "right" });

  for (const id of [
    "world-folder-new",
    "world-folder-copy",
    "world-folder-cut",
    "world-folder-paste",
    "world-folder-rename",
    "world-folder-move",
    "world-folder-merge",
    "world-folder-delete",
  ]) {
    await expect(page.getByTestId(`context-menu-item-${id}`)).toBeVisible();
  }
  await expect(
    page.getByTestId("context-menu-item-world-folder-paste"),
  ).toBeDisabled();
  await expect(
    page.getByTestId("context-menu-item-world-folder-paste"),
  ).toHaveAttribute("title", /not available/i);
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("global-context-menu")).toBeHidden();
  await expect(page.locator("body")).not.toContainText("Categories");
  await expect(page.locator("body")).not.toContainText("Add Category");
  await expect(page.getByTestId("world-category-tree-toggle")).toContainText(
    "Folders",
  );
});

test("cut and paste move the stable world item once and undo restores the complete graph", async ({
  page,
}) => {
  await page.goto("/world");
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.setState((state: any) => ({
      worldContainers: [
        ...state.worldContainers,
        {
          id: "cut_source",
          name: "Cut Source",
          type: "notebook",
          sortOrder: 300,
        },
        {
          id: "cut_target",
          name: "Cut Target",
          type: "notebook",
          sortOrder: 301,
        },
      ],
      worldItems: [
        ...state.worldItems,
        {
          id: "cut_item",
          containerId: "cut_source",
          type: "concept",
          name: "Cut Item",
          description: "",
          attributes: [],
          linkedCharacterIds: [],
          linkedEventIds: [],
          linkedSceneIds: [],
          mapMarkers: [],
          tagIds: [],
        },
        {
          id: "cut_target_item",
          containerId: "cut_target",
          type: "concept",
          name: "Target Item",
          description: "",
          attributes: [],
          linkedCharacterIds: [],
          linkedEventIds: [],
          linkedSceneIds: [],
          mapMarkers: [],
          tagIds: [],
        },
      ],
      characters: [
        ...state.characters,
        { id: "cut_character", linkedWorldItemIds: ["cut_item"] },
      ],
      timelineEvents: [
        ...state.timelineEvents,
        {
          id: "cut_event",
          locationIds: ["cut_item"],
          linkedWorldItemIds: ["cut_item"],
        },
      ],
      scenes: [
        ...state.scenes,
        { id: "cut_scene", linkedWorldItemIds: ["cut_item"] },
      ],
      undoStack: [],
      redoStack: [],
    }));
  });

  await page.getByTestId("world-container-cut_source").click();
  await page.getByTestId("world-item-cut_item").click({ button: "right" });
  await page.getByTestId("context-menu-item-world-item-cut").click();
  await page.getByTestId("world-container-cut_target").click();
  await page
    .getByTestId("world-item-cut_target_item")
    .click({ button: "right" });
  await page.getByTestId("context-menu-item-world-item-paste").click();

  await expect
    .poll(() =>
      page.evaluate(() => {
        const state = (window as any).__narrativeStore.getState();
        return {
          count: state.worldItems.filter((item: any) => item.id === "cut_item")
            .length,
          containerId: state.worldItems.find(
            (item: any) => item.id === "cut_item",
          )?.containerId,
          undoDepth: state.undoStack.length,
          character: state.characters.find(
            (item: any) => item.id === "cut_character",
          ).linkedWorldItemIds,
          event: (() => {
            const event = state.timelineEvents.find(
              (item: any) => item.id === "cut_event",
            );
            return {
              locationIds: event.locationIds,
              linkedWorldItemIds: event.linkedWorldItemIds,
            };
          })(),
          scene: state.scenes.find((item: any) => item.id === "cut_scene")
            .linkedWorldItemIds,
        };
      }),
    )
    .toEqual({
      count: 1,
      containerId: "cut_target",
      undoDepth: 1,
      character: ["cut_item"],
      event: { locationIds: ["cut_item"], linkedWorldItemIds: ["cut_item"] },
      scene: ["cut_item"],
    });

  await page.keyboard.press("Control+Z");
  await expect
    .poll(() =>
      page.evaluate(() => {
        const state = (window as any).__narrativeStore.getState();
        return {
          containerId: state.worldItems.find(
            (item: any) => item.id === "cut_item",
          )?.containerId,
          undoDepth: state.undoStack.length,
        };
      }),
    )
    .toEqual({ containerId: "cut_source", undoDepth: 0 });
});

test("delete cleans world references and one undo restores every reference", async ({
  page,
}) => {
  await page.goto("/world");
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.setState((state: any) => ({
      worldContainers: [
        ...state.worldContainers,
        {
          id: "delete_folder",
          name: "Delete Folder",
          type: "notebook",
          sortOrder: 400,
        },
      ],
      worldItems: [
        ...state.worldItems,
        {
          id: "delete_item",
          containerId: "delete_folder",
          type: "concept",
          name: "Delete Item",
          description: "",
          attributes: [],
          linkedCharacterIds: [],
          linkedEventIds: [],
          linkedSceneIds: [],
          mapMarkers: [],
          tagIds: [],
        },
        {
          id: "marker_item",
          containerId: "delete_folder",
          type: "concept",
          name: "Marker Item",
          description: "",
          attributes: [],
          linkedCharacterIds: [],
          linkedEventIds: [],
          linkedSceneIds: [],
          mapMarkers: [
            {
              id: "marker_ref",
              label: "Ref",
              x: 0,
              y: 0,
              linkedEntityId: "delete_item",
            },
          ],
          tagIds: [],
        },
      ],
      characters: [
        ...state.characters,
        { id: "delete_character", linkedWorldItemIds: ["delete_item"] },
      ],
      timelineEvents: [
        ...state.timelineEvents,
        {
          id: "delete_event",
          locationIds: ["delete_item"],
          linkedWorldItemIds: ["delete_item"],
        },
      ],
      scenes: [
        ...state.scenes,
        { id: "delete_scene", linkedWorldItemIds: ["delete_item"] },
      ],
      undoStack: [],
      redoStack: [],
    }));
  });

  await page.getByTestId("world-container-delete_folder").click();
  await page.getByTestId("world-item-delete_item").click({ button: "right" });
  await page.getByTestId("context-menu-item-world-item-delete").click();
  await page.getByTestId("context-menu-item-world-item-delete").click();

  await expect
    .poll(() =>
      page.evaluate(() => {
        const state = (window as any).__narrativeStore.getState();
        return {
          exists: state.worldItems.some(
            (item: any) => item.id === "delete_item",
          ),
          undoDepth: state.undoStack.length,
          character: state.characters.find(
            (item: any) => item.id === "delete_character",
          ).linkedWorldItemIds,
          event: (() => {
            const event = state.timelineEvents.find(
              (item: any) => item.id === "delete_event",
            );
            return {
              locationIds: event.locationIds,
              linkedWorldItemIds: event.linkedWorldItemIds,
            };
          })(),
          scene: state.scenes.find((item: any) => item.id === "delete_scene")
            .linkedWorldItemIds,
          marker: state.worldItems.find(
            (item: any) => item.id === "marker_item",
          ).mapMarkers[0].linkedEntityId,
        };
      }),
    )
    .toEqual({
      exists: false,
      undoDepth: 1,
      character: [],
      event: { locationIds: [], linkedWorldItemIds: [] },
      scene: [],
      marker: null,
    });

  await page.keyboard.press("Control+Z");
  await expect
    .poll(() =>
      page.evaluate(() => {
        const state = (window as any).__narrativeStore.getState();
        return {
          exists: state.worldItems.some(
            (item: any) => item.id === "delete_item",
          ),
          undoDepth: state.undoStack.length,
          character: state.characters.find(
            (item: any) => item.id === "delete_character",
          ).linkedWorldItemIds,
          event: (() => {
            const event = state.timelineEvents.find(
              (item: any) => item.id === "delete_event",
            );
            return {
              locationIds: event.locationIds,
              linkedWorldItemIds: event.linkedWorldItemIds,
            };
          })(),
          scene: state.scenes.find((item: any) => item.id === "delete_scene")
            .linkedWorldItemIds,
          marker: state.worldItems.find(
            (item: any) => item.id === "marker_item",
          ).mapMarkers[0].linkedEntityId,
        };
      }),
    )
    .toEqual({
      exists: true,
      undoDepth: 0,
      character: ["delete_item"],
      event: {
        locationIds: ["delete_item"],
        linkedWorldItemIds: ["delete_item"],
      },
      scene: ["delete_item"],
      marker: "delete_item",
    });
});

test("deleteWorldContainer cascades child folders, cleans every reference, and undoes atomically", async ({
  page,
}) => {
  await page.goto("/world");
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.setState((state: any) => ({
      worldContainers: [
        ...state.worldContainers,
        {
          id: "cascade_parent",
          name: "Cascade Parent",
          type: "notebook",
          sortOrder: 500,
        },
        {
          id: "cascade_child",
          name: "Cascade Child",
          type: "notebook",
          parentId: "cascade_parent",
          sortOrder: 501,
        },
      ],
      worldItems: [
        ...state.worldItems,
        {
          id: "cascade_parent_item",
          containerId: "cascade_parent",
          type: "concept",
          name: "Parent item",
          description: "",
          attributes: [],
          linkedCharacterIds: [],
          linkedEventIds: [],
          linkedSceneIds: [],
          mapMarkers: [
            { id: "cascade_parent_marker", label: "Parent marker", x: 0, y: 0 },
          ],
          tagIds: [],
        },
        {
          id: "cascade_child_item",
          containerId: "cascade_child",
          type: "concept",
          name: "Child item",
          description: "",
          attributes: [],
          linkedCharacterIds: [],
          linkedEventIds: [],
          linkedSceneIds: [],
          mapMarkers: [
            { id: "cascade_child_marker", label: "Child marker", x: 1, y: 1 },
          ],
          tagIds: [],
        },
        {
          id: "cascade_survivor",
          containerId: "cascade_survivor_folder",
          type: "concept",
          name: "Survivor",
          description: "",
          attributes: [],
          linkedCharacterIds: [],
          linkedEventIds: [],
          linkedSceneIds: [],
          mapMarkers: [
            {
              id: "cascade_reference_marker",
              label: "Reference marker",
              x: 2,
              y: 2,
              linkedEntityId: "cascade_child_item",
            },
          ],
          tagIds: [],
        },
      ],
      worldMaps: [
        ...state.worldMaps,
        {
          id: "cascade_map",
          title: "Cascade map",
          description: "",
          assetPath: null,
          markerIds: [
            "cascade_parent_marker",
            "cascade_child_marker",
            "cascade_reference_marker",
          ],
          sortOrder: 0,
        },
      ],
      characters: [
        ...state.characters,
        {
          id: "cascade_character",
          linkedWorldItemIds: ["cascade_parent_item", "cascade_child_item"],
        },
      ],
      timelineEvents: [
        ...state.timelineEvents,
        {
          id: "cascade_event",
          locationIds: ["cascade_parent_item"],
          linkedWorldItemIds: ["cascade_child_item"],
        },
      ],
      scenes: [
        ...state.scenes,
        { id: "cascade_scene", linkedWorldItemIds: ["cascade_child_item"] },
      ],
      scripts: [
        ...state.scripts,
        { id: "cascade_script", linkedWorldItemIds: ["cascade_parent_item"] },
      ],
      storyboards: [
        ...state.storyboards,
        {
          id: "cascade_storyboard",
          shots: [
            { id: "cascade_shot", linkedWorldItemIds: ["cascade_child_item"] },
          ],
        },
      ],
      graphBoards: [
        ...state.graphBoards,
        {
          id: "cascade_graph",
          name: "Cascade graph",
          description: "",
          sortOrder: 99,
          selectedNodeIds: [],
          edges: [],
          view: { zoom: 1, panX: 0, panY: 0 },
          nodes: [
            {
              id: "cascade_node",
              kind: "world_item_ref",
              label: "Child ref",
              description: "",
              x: 0,
              y: 0,
              width: 100,
              height: 80,
              linkedEntityId: "cascade_child_item",
              linkedEntityType: "world_item",
            },
          ],
        },
      ],
      undoStack: [],
      redoStack: [],
    }));
    store.getState().deleteWorldContainer("cascade_parent");
  });

  await expect
    .poll(() =>
      page.evaluate(() => {
        const state = (window as any).__narrativeStore.getState();
        return {
          containers: state.worldContainers
            .filter((item: any) => item.id.startsWith("cascade_"))
            .map((item: any) => item.id),
          items: state.worldItems
            .filter((item: any) => item.id.startsWith("cascade_"))
            .map((item: any) => item.id),
          character: state.characters.find(
            (item: any) => item.id === "cascade_character",
          ).linkedWorldItemIds,
          event: (() => {
            const event = state.timelineEvents.find(
              (item: any) => item.id === "cascade_event",
            );
            return {
              id: event.id,
              locationIds: event.locationIds,
              linkedWorldItemIds: event.linkedWorldItemIds,
            };
          })(),
          scene: state.scenes.find((item: any) => item.id === "cascade_scene")
            .linkedWorldItemIds,
          script: state.scripts.find(
            (item: any) => item.id === "cascade_script",
          ).linkedWorldItemIds,
          storyboard: state.storyboards.find(
            (item: any) => item.id === "cascade_storyboard",
          ).shots[0].linkedWorldItemIds,
          graph: state.graphBoards.find(
            (item: any) => item.id === "cascade_graph",
          ).nodes[0].linkedEntityId,
          marker: state.worldItems.find(
            (item: any) => item.id === "cascade_survivor",
          ).mapMarkers[0].linkedEntityId,
          mapMarkers: state.worldMaps.find(
            (item: any) => item.id === "cascade_map",
          ).markerIds,
          undoDepth: state.undoStack.length,
        };
      }),
    )
    .toEqual({
      containers: [],
      items: ["cascade_survivor"],
      character: [],
      event: { id: "cascade_event", locationIds: [], linkedWorldItemIds: [] },
      scene: [],
      script: [],
      storyboard: [],
      graph: null,
      marker: null,
      mapMarkers: ["cascade_reference_marker"],
      undoDepth: 1,
    });

  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });
  await expect
    .poll(() =>
      page.evaluate(() => {
        const state = (window as any).__narrativeStore.getState();
        return {
          containers: state.worldContainers
            .filter((item: any) => item.id.startsWith("cascade_"))
            .map((item: any) => item.id)
            .sort(),
          items: state.worldItems
            .filter((item: any) => item.id.startsWith("cascade_"))
            .map((item: any) => item.id)
            .sort(),
          character: state.characters.find(
            (item: any) => item.id === "cascade_character",
          ).linkedWorldItemIds,
          event: (() => {
            const event = state.timelineEvents.find(
              (item: any) => item.id === "cascade_event",
            );
            return {
              id: event.id,
              locationIds: event.locationIds,
              linkedWorldItemIds: event.linkedWorldItemIds,
            };
          })(),
          scene: state.scenes.find((item: any) => item.id === "cascade_scene")
            .linkedWorldItemIds,
          script: state.scripts.find(
            (item: any) => item.id === "cascade_script",
          ).linkedWorldItemIds,
          storyboard: state.storyboards.find(
            (item: any) => item.id === "cascade_storyboard",
          ).shots[0].linkedWorldItemIds,
          graph: state.graphBoards.find(
            (item: any) => item.id === "cascade_graph",
          ).nodes[0].linkedEntityId,
          marker: state.worldItems.find(
            (item: any) => item.id === "cascade_survivor",
          ).mapMarkers[0].linkedEntityId,
          mapMarkers: state.worldMaps.find(
            (item: any) => item.id === "cascade_map",
          ).markerIds,
          undoDepth: state.undoStack.length,
        };
      }),
    )
    .toEqual({
      containers: ["cascade_child", "cascade_parent"],
      items: ["cascade_child_item", "cascade_parent_item", "cascade_survivor"],
      character: ["cascade_parent_item", "cascade_child_item"],
      event: {
        id: "cascade_event",
        locationIds: ["cascade_parent_item"],
        linkedWorldItemIds: ["cascade_child_item"],
      },
      scene: ["cascade_child_item"],
      script: ["cascade_parent_item"],
      storyboard: ["cascade_child_item"],
      graph: "cascade_child_item",
      marker: "cascade_child_item",
      mapMarkers: [
        "cascade_parent_marker",
        "cascade_child_marker",
        "cascade_reference_marker",
      ],
      undoDepth: 0,
    });
});
